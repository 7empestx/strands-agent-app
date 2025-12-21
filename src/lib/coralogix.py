"""Coralogix log analysis tools for MCP server.

Provides natural language → DataPrime query conversion and execution.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests

# Add project root to path to import shared utils
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from src.lib.utils.secrets import get_secret

# Configuration
# Coralogix API endpoint (MrRobot uses cx498 region)
CORALOGIX_ENDPOINT = "https://ng-api-http.cx498.coralogix.com"

# =============================================================================
# NATURAL LANGUAGE → DATAPRIME CONVERSION
# =============================================================================

# Keywords for intent detection
ERROR_KEYWORDS = ["error", "exception", "fail", "crash", "fatal", "critical", "warn"]
METRIC_KEYWORDS = ["count", "sum", "avg", "average", "max", "min", "total"]
TIME_KEYWORDS = {"hour": 1, "hours": 1, "day": 24, "days": 24, "week": 168, "minute": 0.017}

# Environment patterns
ENV_PATTERNS = {
    "prod": "-prod",
    "production": "-prod",
    "sandbox": "-sandbox",
    "dev": "-dev",
    "development": "-dev",
    "staging": "-staging",
    "stage": "-staging",
}

# Service name patterns
SERVICE_PATTERNS = [
    r"(cast-\w+)",
    r"(emvio-\w+)",
    r"(mrrobot-\w+)",
    r"(lambda-\w+)",
    r"([a-z]+-service)",
    r"([a-z]+-api)",
]


def natural_language_to_dataprime(query: str, limit: int = 50) -> dict:
    """Convert natural language to a DataPrime query.

    Args:
        query: Natural language query (e.g., "show errors in prod for cast-core")
        limit: Max results to return

    Returns:
        dict with 'dataprime_query' and 'explanation'
    """
    query_lower = query.lower()
    filters = []
    explanation = []
    message_filters = []  # Separate list for message content filters

    # 1. Detect error-related queries
    found_errors = [kw for kw in ERROR_KEYWORDS if kw in query_lower]
    if found_errors:
        error_conditions = " || ".join([f"message ~ '{kw}'" for kw in found_errors])
        message_filters.append(f"({error_conditions})")
        explanation.append(f"Filtering for: {', '.join(found_errors)}")

    # 2. Detect environment
    for env_name, env_pattern in ENV_PATTERNS.items():
        if env_name in query_lower:
            filters.append(f"logGroup ~ '{env_pattern}'")
            explanation.append(f"Environment: {env_name}")
            break

    # 3. Detect service names
    for pattern in SERVICE_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            service = match.group(1)
            filters.append(f"logGroup ~ '{service}'")
            explanation.append(f"Service: {service}")
            break

    # 4. Detect specific search terms (quoted strings)
    quoted_terms = re.findall(r'"([^"]+)"', query)
    for term in quoted_terms:
        message_filters.append(f"message ~ '{term}'")
        explanation.append(f"Search term: '{term}'")

    # 5. Detect HTTP status codes (e.g., 504, 500, 403, 401, 200)
    status_codes = re.findall(r'\b(5\d{2}|4\d{2}|[23]\d{2})\b', query)
    for code in status_codes:
        message_filters.append(f"message ~ '{code}'")
        explanation.append(f"HTTP status: {code}")

    # 6. Detect specific technical terms that should be searched in message
    technical_terms = [
        "timeout", "connection refused", "connection reset", "ECONNREFUSED",
        "ETIMEDOUT", "ENOTFOUND", "socket hang up", "gateway", "upstream",
        "lambda", "invocation", "cold start", "memory", "duration",
        "unauthorized", "forbidden", "access denied", "permission",
        "null", "undefined", "NaN", "stack trace", "stacktrace",
        "deadlock", "out of memory", "OOM", "killed", "SIGKILL",
        "CORS", "preflight", "content-type", "content-security-policy",
        "syncAll", "webhook", "integrationJob", "sync"
    ]
    for term in technical_terms:
        if term.lower() in query_lower:
            message_filters.append(f"message ~ '{term}'")
            explanation.append(f"Technical term: {term}")

    # 7. Detect UUIDs/orgIds in the query
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    uuids = re.findall(uuid_pattern, query_lower)
    for uuid in uuids:
        message_filters.append(f"message ~ '{uuid}'")
        explanation.append(f"UUID/ID: {uuid}")

    # 8. Detect specific endpoints/paths
    path_patterns = re.findall(r'(/[\w/]+(?:/\w+)*)', query)
    for path in path_patterns:
        if len(path) > 3:  # Avoid matching just "/"
            message_filters.append(f"message ~ '{path}'")
            explanation.append(f"Endpoint: {path}")

    # 9. Detect aggregation intent
    aggregation = None
    if any(kw in query_lower for kw in ["count", "how many", "total"]):
        aggregation = "groupby logGroup | count | sort -_count"
        explanation.append("Aggregation: count by service")
    elif "group by" in query_lower or "grouped" in query_lower:
        aggregation = "groupby logGroup | count"
        explanation.append("Aggregation: grouped by service")

    # Combine all filters
    all_filters = filters + message_filters

    # Build the DataPrime query
    if all_filters:
        filter_str = " && ".join(all_filters)
        dataprime = f"source logs | filter {filter_str}"
    else:
        # Default: search for significant words in the query
        stopwords = ["show", "find", "search", "logs", "from", "with", "the",
                     "for", "and", "check", "look", "get", "see", "any", "errors",
                     "please", "can", "you", "help", "debug", "issue", "problem"]
        words = [w for w in query_lower.split() if len(w) > 3 and w not in stopwords]
        if words:
            # Use the first 2 significant words
            word_filters = [f"message ~ '{w}'" for w in words[:2]]
            dataprime = f"source logs | filter {' && '.join(word_filters)}"
            explanation.append(f"Searching for: {', '.join(words[:2])}")
        else:
            dataprime = "source logs"
            explanation.append("No specific filter - returning recent logs")

    # Add aggregation or limit
    if aggregation:
        dataprime += f" | {aggregation} | limit {limit}"
    else:
        dataprime += f" | limit {limit}"

    return {
        "dataprime_query": dataprime,
        "original_query": query,
        "explanation": explanation,
    }


def execute_natural_language_query(
    query: str,
    hours_back: int = 4,
    limit: int = 50,
) -> dict:
    """Execute a natural language query against Coralogix.

    Args:
        query: Natural language query
        hours_back: Hours of logs to search
        limit: Max results

    Returns:
        dict with query info and results
    """
    # Convert to DataPrime
    conversion = natural_language_to_dataprime(query, limit)
    dataprime_query = conversion["dataprime_query"]

    # Execute
    response = _make_request(dataprime_query, hours_back, limit)
    logs = _parse_response(response)

    return {
        "query": query,
        "dataprime_query": dataprime_query,
        "explanation": conversion["explanation"],
        "time_range": f"Last {hours_back} hour(s)",
        "total_results": len(logs),
        "logs": logs[:limit],
    }


def _get_api_key() -> str:
    """Get Coralogix API key."""
    return get_secret("CORALOGIX_AGENT_KEY") or get_secret("CORALOGIX_API_KEY")


def _get_endpoint() -> str:
    """Get Coralogix API endpoint."""
    return CORALOGIX_ENDPOINT


def _make_request(query: str, hours_back: int = 4, limit: int = 100) -> dict:
    """Make a request to Coralogix DataPrime API."""
    api_key = _get_api_key()
    if not api_key:
        print("[Coralogix] ERROR: No API key configured")
        return {"error": "CORALOGIX_API_KEY not configured"}

    endpoint = _get_endpoint()
    url = f"{endpoint}/api/v1/dataprime/query"
    print(f"[Coralogix] Making request to: {url}")
    print(f"[Coralogix] Query: {query}")

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    headers = {
        "Authorization": f"Bearer {api_key[:10]}...",  # Log only partial key
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
    print(f"[Coralogix] Time range: {start_time.isoformat()} to {end_time.isoformat()}")

    # Use actual key in request (not the truncated one)
    actual_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=actual_headers, json=payload, timeout=30)
        print(f"[Coralogix] Response status: {response.status_code}")
        response.raise_for_status()
        results = []
        response_lines = response.text.strip().split("\n")
        print(f"[Coralogix] Response has {len(response_lines)} lines")
        for line in response_lines:
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"[Coralogix] Failed to parse line: {line[:100]}")
        print(f"[Coralogix] Parsed {len(results)} result objects")
        return {"results": results}
    except requests.exceptions.RequestException as e:
        print(f"[Coralogix] API request failed: {str(e)}")
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
        services.append(
            {
                "log_group": lg,
                "service_name": service_name,
                "is_cast": "cast" in lg.lower(),
            }
        )

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

    errors_by_service = {}
    for log in logs:
        log_group = log.get("logGroup", "unknown")
        parts = log_group.split("/")
        service = parts[-1] if parts else log_group

        if service not in errors_by_service:
            errors_by_service[service] = []
        errors_by_service[service].append(
            {
                "message": log.get("message", ""),
                "timestamp": log.get("timestamp"),
                "logGroup": log_group,
            }
        )

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
    """Search logs using natural language or DataPrime.

    Accepts either:
    - Natural language: "show errors in prod for cast-core"
    - DataPrime: "source logs | filter message ~ 'error' | limit 50"

    Args:
        query: Natural language or DataPrime query
        hours_back: Hours of logs to search
        limit: Max results

    Returns:
        dict with query info and results
    """
    print(f"[Coralogix] handle_search_logs called with query: '{query}'")
    
    # Check if it's already a DataPrime query (starts with 'source')
    if query.strip().lower().startswith("source"):
        print("[Coralogix] Detected raw DataPrime query")
        # Execute raw DataPrime
        response = _make_request(query, hours_back, min(limit, 500))
        logs = _parse_response(response)
        print(f"[Coralogix] Raw query returned {len(logs)} logs")
        return {
            "query": query,
            "dataprime_query": query,
            "time_range": f"Last {hours_back} hour(s)",
            "total_results": len(logs),
            "logs": logs[:limit],
        }
    else:
        # Convert natural language to DataPrime and execute
        print("[Coralogix] Converting natural language to DataPrime")
        result = execute_natural_language_query(query, hours_back, limit)
        print(f"[Coralogix] Converted to: {result.get('dataprime_query', 'N/A')}")
        print(f"[Coralogix] Result has {result.get('total_results', 0)} logs")
        return result


def handle_get_service_health(service_name: str = "all", environment: str = "prod") -> dict:
    """Get health overview based on error rates."""
    total_filters = []
    if service_name.lower() != "all":
        total_filters.append(f"logGroup ~ '{service_name}'")
    if environment.lower() != "all":
        total_filters.append(f"logGroup ~ '-{environment.lower()}'")

    total_filter_str = " && ".join(total_filters) if total_filters else "true"
    total_query = f"source logs | filter {total_filter_str} | groupby logGroup | count | sort -_count | limit 20"

    total_response = _make_request(total_query, 1, 20)
    total_logs = _parse_response(total_response)

    error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception'"
    error_filters = total_filters + [f"({error_patterns})"]
    error_filter_str = " && ".join(error_filters)
    error_query = f"source logs | filter {error_filter_str} | groupby logGroup | count | sort -_count | limit 20"

    error_response = _make_request(error_query, 1, 20)
    error_logs = _parse_response(error_response)

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

        health_results.append(
            {
                "service": service,
                "status": status,
                "log_count": total,
                "error_count": errors,
                "error_rate_percent": round(error_rate, 2),
            }
        )

    return {
        "environment": environment,
        "time_range": "Last 1 hour",
        "services_checked": len(health_results),
        "health_summary": health_results,
    }
