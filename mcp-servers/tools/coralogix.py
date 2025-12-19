"""Coralogix log analysis tools for MCP server."""

import json
import os
from datetime import datetime, timedelta

import requests

from ..utils.secrets import get_secret

# Configuration
CORALOGIX_REGION = os.environ.get("CORALOGIX_REGION", "us2")

CORALOGIX_ENDPOINTS = {
    "us1": "https://ng-api-http.us1.coralogix.com",
    "us2": "https://ng-api-http.cx498.coralogix.com",
    "eu1": "https://ng-api-http.eu1.coralogix.com",
    "eu2": "https://ng-api-http.eu2.coralogix.com",
}


def _get_api_key() -> str:
    """Get Coralogix API key."""
    return get_secret("CORALOGIX_AGENT_KEY") or get_secret("CORALOGIX_API_KEY")


def _get_endpoint() -> str:
    """Get Coralogix API endpoint."""
    return CORALOGIX_ENDPOINTS.get(CORALOGIX_REGION, CORALOGIX_ENDPOINTS["us2"])


def _make_request(query: str, hours_back: int = 4, limit: int = 100) -> dict:
    """Make a request to Coralogix DataPrime API."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "CORALOGIX_API_KEY not configured"}

    endpoint = _get_endpoint()
    url = f"{endpoint}/api/v1/dataprime/query"

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "metadata": {
            "startDate": start_time.isoformat() + "Z",
            "endDate": end_time.isoformat() + "Z",
            "tier": "TIER_FREQUENT_SEARCH",
            "limit": limit,
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        # Handle NDJSON response
        results = []
        for line in response.text.strip().split("\n"):
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return {"results": results}
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}


def _parse_response(response: dict) -> list:
    """Parse Coralogix API response into log entries."""
    if "error" in response:
        return [response]

    logs = []
    for item in response.get("results", []):
        if "result" not in item:
            continue
        results = item.get("result", {}).get("results", [])
        for result in results:
            if "userData" in result:
                try:
                    logs.append(json.loads(result["userData"]))
                except json.JSONDecodeError:
                    logs.append(result)
            else:
                log_entry = {}
                for key, value in result.items():
                    if isinstance(value, dict) and "value" in value:
                        log_entry[key] = value["value"]
                    else:
                        log_entry[key] = value
                logs.append(log_entry)
    return logs


# Tool handlers
def handle_discover_services(hours_back: int = 1, limit: int = 50) -> dict:
    """Discover available log groups/services."""
    query = f"source logs | distinct logGroup | limit {limit}"
    response = _make_request(query, hours_back, limit)
    logs = _parse_response(response)

    log_groups = set()
    for log in logs:
        lg = log.get("logGroup", "")
        if lg:
            log_groups.add(lg)

    services = []
    for lg in sorted(log_groups):
        parts = lg.split("/")
        service_name = parts[-1] if parts else lg
        services.append({
            "log_group": lg,
            "service_name": service_name,
            "is_cast": "cast" in lg.lower(),
        })

    return {
        "time_range": f"Last {hours_back} hour(s)",
        "total_services": len(services),
        "cast_services": [s for s in services if s["is_cast"]],
        "other_services": [s for s in services if not s["is_cast"]],
    }


def handle_get_recent_errors(
    service_name: str = "all",
    hours_back: int = 4,
    limit: int = 100,
    environment: str = "all",
) -> dict:
    """Get recent errors from logs."""
    error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception' || message ~ 'FATAL'"

    filters = [f"({error_patterns})"]
    if service_name.lower() != "all":
        filters.append(f"logGroup ~ '{service_name}'")
    if environment.lower() != "all":
        filters.append(f"logGroup ~ '-{environment.lower()}'")

    filter_str = " && ".join(filters)
    query = f"source logs | filter {filter_str} | limit {limit}"

    response = _make_request(query, hours_back, limit)
    logs = _parse_response(response)

    # Group by service
    errors_by_service = {}
    for log in logs:
        log_group = log.get("logGroup", "unknown")
        parts = log_group.split("/")
        service = parts[-1] if parts else log_group

        if service not in errors_by_service:
            errors_by_service[service] = []
        errors_by_service[service].append({
            "message": log.get("message", ""),
            "timestamp": log.get("timestamp"),
            "logGroup": log_group,
        })

    return {
        "environment": environment,
        "filter": service_name,
        "time_range": f"Last {hours_back} hour(s)",
        "total_errors": len(logs),
        "services_with_errors": len(errors_by_service),
        "errors_by_service": {
            svc: {"count": len(errs), "recent_errors": errs[:10]}
            for svc, errs in sorted(errors_by_service.items(), key=lambda x: -len(x[1]))
        },
    }


def handle_get_service_logs(
    service_name: str,
    hours_back: int = 1,
    error_only: bool = False,
    limit: int = 50,
    environment: str = "all",
) -> dict:
    """Get logs for a specific service."""
    filters = [f"logGroup ~ '{service_name}'"]
    if environment.lower() != "all":
        filters.append(f"logGroup ~ '-{environment.lower()}'")
    if error_only:
        error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception'"
        filters.append(f"({error_patterns})")

    filter_str = " && ".join(filters)
    query = f"source logs | filter {filter_str} | limit {limit}"

    response = _make_request(query, hours_back, limit)
    logs = _parse_response(response)

    return {
        "service": service_name,
        "environment": environment,
        "error_only": error_only,
        "time_range": f"Last {hours_back} hour(s)",
        "total_results": len(logs),
        "logs": logs,
    }


def handle_search_logs(query: str, hours_back: int = 4, limit: int = 100) -> dict:
    """Execute a DataPrime query."""
    response = _make_request(query, hours_back, min(limit, 500))
    logs = _parse_response(response)

    return {
        "query": query,
        "time_range": f"Last {hours_back} hour(s)",
        "total_results": len(logs),
        "logs": logs[:limit],
    }


def handle_get_service_health(service_name: str = "all", environment: str = "prod") -> dict:
    """Get health overview based on error rates."""
    # Get total counts
    total_filters = []
    if service_name.lower() != "all":
        total_filters.append(f"logGroup ~ '{service_name}'")
    if environment.lower() != "all":
        total_filters.append(f"logGroup ~ '-{environment.lower()}'")

    total_filter_str = " && ".join(total_filters) if total_filters else "true"
    total_query = f"source logs | filter {total_filter_str} | groupby logGroup | count | sort -_count | limit 20"

    total_response = _make_request(total_query, 1, 20)
    total_logs = _parse_response(total_response)

    # Get error counts
    error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception'"
    error_filters = total_filters + [f"({error_patterns})"]
    error_filter_str = " && ".join(error_filters)
    error_query = f"source logs | filter {error_filter_str} | groupby logGroup | count | sort -_count | limit 20"

    error_response = _make_request(error_query, 1, 20)
    error_logs = _parse_response(error_response)

    # Build counts
    total_counts = {}
    for log in total_logs:
        lg = log.get("logGroup", "")
        parts = lg.split("/")
        service = parts[-1] if parts else lg
        total_counts[service] = log.get("_count", 0)

    error_counts = {}
    for log in error_logs:
        lg = log.get("logGroup", "")
        parts = lg.split("/")
        service = parts[-1] if parts else lg
        error_counts[service] = log.get("_count", 0)

    # Calculate health
    health_results = []
    for service, total in sorted(total_counts.items(), key=lambda x: -x[1]):
        errors = error_counts.get(service, 0)
        error_rate = (errors / total * 100) if total > 0 else 0

        if error_rate > 10:
            status = "CRITICAL"
        elif error_rate > 5:
            status = "WARNING"
        else:
            status = "HEALTHY"

        health_results.append({
            "service": service,
            "status": status,
            "log_count": total,
            "error_count": errors,
            "error_rate_percent": round(error_rate, 2),
        })

    return {
        "environment": environment,
        "time_range": "Last 1 hour",
        "services_checked": len(health_results),
        "health_summary": health_results,
    }


def register_coralogix_tools(protocol):
    """Register all Coralogix tools with the MCP protocol handler."""

    protocol.register_tool(
        name="coralogix_discover_services",
        description="Discover available log groups/services in Coralogix.",
        input_schema={
            "type": "object",
            "properties": {
                "hours_back": {"type": "integer", "default": 1, "description": "Hours to search back"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        handler=handle_discover_services,
    )

    protocol.register_tool(
        name="coralogix_get_recent_errors",
        description="Get recent errors from Coralogix logs, grouped by service.",
        input_schema={
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "default": "all", "description": "Service name or 'all'"},
                "hours_back": {"type": "integer", "default": 4},
                "limit": {"type": "integer", "default": 100},
                "environment": {"type": "string", "default": "all", "description": "prod, dev, staging, or all"},
            },
            "required": [],
        },
        handler=handle_get_recent_errors,
    )

    protocol.register_tool(
        name="coralogix_get_service_logs",
        description="Get logs for a specific service from Coralogix.",
        input_schema={
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Service name pattern"},
                "hours_back": {"type": "integer", "default": 1},
                "error_only": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 50},
                "environment": {"type": "string", "default": "all"},
            },
            "required": ["service_name"],
        },
        handler=handle_get_service_logs,
    )

    protocol.register_tool(
        name="coralogix_search_logs",
        description="Execute a custom DataPrime query on Coralogix logs.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "DataPrime query (e.g., source logs | filter message ~ 'error')"},
                "hours_back": {"type": "integer", "default": 4},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["query"],
        },
        handler=handle_search_logs,
    )

    protocol.register_tool(
        name="coralogix_get_service_health",
        description="Get health overview for services based on error rates.",
        input_schema={
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "default": "all"},
                "environment": {"type": "string", "default": "prod"},
            },
            "required": [],
        },
        handler=handle_get_service_health,
    )

