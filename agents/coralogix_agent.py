"""
Coralogix Log Analysis Agent
Uses Strands SDK with Claude Sonnet on Amazon Bedrock
"""

import json
import os
from datetime import datetime, timedelta

import requests
from strands import Agent, tool

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
CORALOGIX_API_KEY = os.environ.get("CORALOGIX_AGENT_KEY", "")
CORALOGIX_REGION = os.environ.get("CORALOGIX_REGION", "us2")  # MrRobot is on US2 (cx498)

# Coralogix API endpoints by region
CORALOGIX_ENDPOINTS = {
    "us1": "https://ng-api-http.us1.coralogix.com",
    "us2": "https://ng-api-http.cx498.coralogix.com",  # MrRobot's region
    "eu1": "https://ng-api-http.eu1.coralogix.com",
    "eu2": "https://ng-api-http.eu2.coralogix.com",
    "ap1": "https://ng-api-http.app.coralogix.in",
    "ap2": "https://ng-api-http.coralogixsg.com",
}

# For backwards compatibility with app.py
KNOWN_SERVICES = {
    "cast-core": {"logGroup": "mrrobot-cast-core", "description": "Core Cast service"},
    "cast-quickbooks": {"logGroup": "mrrobot-cast-quickbooks", "description": "QuickBooks integration"},
    "cast-housecallpro": {"logGroup": "mrrobot-cast-housecallpro", "description": "HouseCall Pro integration"},
    "cast-jobber": {"logGroup": "mrrobot-cast-jobber", "description": "Jobber integration"},
    "cast-service-titan": {"logGroup": "mrrobot-cast-service-titan", "description": "Service Titan integration"},
    "cast-mhelpdesk": {"logGroup": "mrrobot-cast-mhelpdesk", "description": "mHelpDesk integration"},
    "cast-xero": {"logGroup": "mrrobot-cast-xero", "description": "Xero accounting integration"},
    "payment-service": {"logGroup": "emvio-payment-service", "description": "Payment processing service"},
    "auth-service": {"logGroup": "emvio-auth-service", "description": "Authentication service"},
    "user-service": {"logGroup": "emvio-user-mgt-service", "description": "User management service"},
    "transactions-service": {"logGroup": "emvio-transactions-service", "description": "Transaction processing"},
    "dashboard": {"logGroup": "emvio-dashboard-app", "description": "Dashboard application"},
    "webhook-service": {"logGroup": "emvio-webhook-service", "description": "Webhook handling"},
}


def get_coralogix_endpoint():
    """Get the Coralogix API endpoint for the configured region."""
    return CORALOGIX_ENDPOINTS.get(CORALOGIX_REGION, CORALOGIX_ENDPOINTS["us1"])


def make_coralogix_request(query: str, start_time: datetime, end_time: datetime, limit: int = 100):
    """Make a request to the Coralogix Logs Query API."""
    if not CORALOGIX_API_KEY:
        return {"error": "CORALOGIX_API_KEY environment variable not set"}

    endpoint = get_coralogix_endpoint()
    url = f"{endpoint}/api/v1/dataprime/query"

    headers = {
        "Authorization": f"Bearer {CORALOGIX_API_KEY}",
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
        # Handle NDJSON response (newline-delimited JSON)
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


def parse_coralogix_response(response: dict) -> list:
    """Parse Coralogix API response into a list of log entries."""
    if "error" in response:
        return [response]

    logs = []
    ndjson_results = response.get("results", [])

    for item in ndjson_results:
        if "result" not in item:
            continue

        results = item.get("result", {}).get("results", [])
        for result in results:
            # userData contains the actual log data as JSON string
            if "userData" in result:
                try:
                    log_entry = json.loads(result["userData"])
                    logs.append(log_entry)
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


# =============================================================================
# TOOLS
# =============================================================================


@tool
def discover_services(hours_back: int = 1, limit: int = 50) -> str:
    """Discover available log groups/services in Coralogix.

    Args:
        hours_back: How many hours back to search (default: 1)
        limit: Maximum number of unique values to return (default: 50)

    Returns:
        str: JSON with list of log groups found, grouped by type (cast vs other)
    """
    print(f"[Tool] discover_services: hours_back={hours_back}")

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    query = f"source logs | distinct logGroup | limit {limit}"
    response = make_coralogix_request(query, start_time, end_time, limit)
    logs = parse_coralogix_response(response)

    # Extract unique log groups
    log_groups = set()
    for log in logs:
        lg = log.get("logGroup", "")
        if lg:
            log_groups.add(lg)

    # Parse log groups to extract service names
    services = []
    for lg in sorted(log_groups):
        parts = lg.split("/")
        service_name = parts[-1] if parts else lg
        services.append({"log_group": lg, "service_name": service_name, "is_cast": "cast" in lg.lower()})

    result = {
        "time_range": f"Last {hours_back} hour(s)",
        "total_services": len(services),
        "cast_services": [s for s in services if s["is_cast"]],
        "other_services": [s for s in services if not s["is_cast"]],
    }

    print(f"[Tool] Found {len(services)} log groups/services")
    return json.dumps(result, indent=2, default=str)


@tool
def get_recent_errors(
    service_name: str = "all", hours_back: int = 4, limit: int = 100, scope: str = "all", environment: str = "all"
) -> str:
    """Get recent errors from logs by searching message content.

    Args:
        service_name: Service name pattern (from logGroup), or 'all' for all services
        hours_back: How many hours back to search (default: 4)
        limit: Maximum number of results (default: 100)
        scope: Filter scope - 'all' (any service), 'cast' (cast services only)
        environment: Environment filter - 'all', 'prod', 'dev', 'staging', etc.

    Returns:
        str: JSON with error logs grouped by service
    """
    print(
        f"[Tool] get_recent_errors: service={service_name}, hours_back={hours_back}, scope={scope}, environment={environment}"
    )

    error_patterns = (
        "message ~ 'ERROR' || message ~ 'Error' || message ~ 'error' || message ~ 'Exception' || message ~ 'FATAL'"
    )

    # Environment filter
    env_filter = ""
    if environment.lower() != "all":
        env_filter = f" && logGroup ~ '-{environment.lower()}'"

    if service_name.lower() == "all":
        if scope == "cast":
            query = f"source logs | filter logGroup ~ 'cast'{env_filter} && ({error_patterns}) | limit {limit}"
        else:
            if env_filter:
                query = f"source logs | filter ({error_patterns}){env_filter} | limit {limit}"
            else:
                query = f"source logs | filter {error_patterns} | limit {limit}"
    else:
        query = f"source logs | filter logGroup ~ '{service_name}'{env_filter} && ({error_patterns}) | limit {limit}"

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    response = make_coralogix_request(query, start_time, end_time, limit)
    logs = parse_coralogix_response(response)

    # Group errors by service
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
                "requestID": log.get("requestID", ""),
            }
        )

    result = {
        "scope": scope,
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

    print(f"[Tool] Found {len(logs)} errors across {len(errors_by_service)} services")
    return json.dumps(result, indent=2, default=str)


@tool
def get_service_logs(
    service_name: str, hours_back: int = 1, error_only: bool = False, limit: int = 50, environment: str = "all"
) -> str:
    """Get logs for a specific service by filtering on logGroup.

    Args:
        service_name: Service name pattern to match in logGroup (e.g., 'cast-core', 'payment')
        hours_back: How many hours back to search (default: 1)
        error_only: If True, only return error logs (default: False)
        limit: Maximum number of results (default: 50)
        environment: Environment filter - 'all', 'prod', 'dev', etc.

    Returns:
        str: JSON with log entries for the service
    """
    print(
        f"[Tool] get_service_logs: service={service_name}, hours_back={hours_back}, error_only={error_only}, environment={environment}"
    )

    # Build filter
    filters = [f"logGroup ~ '{service_name}'"]

    if environment.lower() != "all":
        filters.append(f"logGroup ~ '-{environment.lower()}'")

    if error_only:
        error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception' || message ~ 'FATAL'"
        filters.append(f"({error_patterns})")

    filter_str = " && ".join(filters)
    query = f"source logs | filter {filter_str} | limit {limit}"

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    response = make_coralogix_request(query, start_time, end_time, limit)
    logs = parse_coralogix_response(response)

    result = {
        "service": service_name,
        "environment": environment,
        "error_only": error_only,
        "time_range": f"Last {hours_back} hour(s)",
        "total_results": len(logs),
        "logs": logs,
    }

    print(f"[Tool] Found {len(logs)} log entries for {service_name}")
    return json.dumps(result, indent=2, default=str)


@tool
def get_log_count(
    service_name: str = "all",
    hours_back: int = 1,
    scope: str = "all",
    environment: str = "all",
    count_errors_only: bool = False,
) -> str:
    """Get log counts for services - useful for volume analysis and trends.

    Args:
        service_name: Service name pattern, or 'all' for all services
        hours_back: How many hours back to search (default: 1)
        scope: Filter scope - 'all' (any service), 'cast' (cast services only)
        environment: Environment filter - 'all', 'prod', 'dev', etc.
        count_errors_only: If True, only count error logs (default: False)

    Returns:
        str: JSON with log counts grouped by service
    """
    print(
        f"[Tool] get_log_count: service={service_name}, hours_back={hours_back}, scope={scope}, environment={environment}, errors_only={count_errors_only}"
    )

    # Build filter
    filters = []

    if service_name.lower() != "all":
        filters.append(f"logGroup ~ '{service_name}'")
    elif scope == "cast":
        filters.append("logGroup ~ 'cast'")

    if environment.lower() != "all":
        filters.append(f"logGroup ~ '-{environment.lower()}'")

    if count_errors_only:
        error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception' || message ~ 'FATAL'"
        filters.append(f"({error_patterns})")

    filter_str = " && ".join(filters) if filters else "true"
    query = f"source logs | filter {filter_str} | groupby logGroup | count | sort -_count | limit 50"

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    response = make_coralogix_request(query, start_time, end_time, 50)
    logs = parse_coralogix_response(response)

    # Parse counts
    counts = []
    total = 0
    for log in logs:
        lg = log.get("logGroup", "unknown")
        parts = lg.split("/")
        service = parts[-1] if parts else lg
        count = log.get("_count", 0)
        total += count
        counts.append({"service": service, "log_group": lg, "count": count})

    result = {
        "scope": scope,
        "environment": environment,
        "count_type": "errors" if count_errors_only else "all_logs",
        "time_range": f"Last {hours_back} hour(s)",
        "total_count": total,
        "services": len(counts),
        "counts_by_service": counts,
    }

    print(f"[Tool] Found {total} logs across {len(counts)} services")
    return json.dumps(result, indent=2, default=str)


@tool
def search_logs(query: str, hours_back: int = 1, limit: int = 50) -> str:
    """Execute a custom DataPrime query for advanced log searches.

    Args:
        query: DataPrime query (e.g., "source logs | filter message ~ 'timeout' | limit 20")
        hours_back: How many hours back to search (default: 1)
        limit: Maximum number of results (default: 50, max: 500)

    Returns:
        str: JSON with log entries matching the query
    """
    print(f"[Tool] search_logs: query='{query}', hours_back={hours_back}")

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    response = make_coralogix_request(query, start_time, end_time, min(limit, 500))
    logs = parse_coralogix_response(response)

    result = {
        "query": query,
        "time_range": f"Last {hours_back} hour(s)",
        "total_results": len(logs),
        "logs": logs[:limit],
    }

    print(f"[Tool] Found {len(logs)} log entries")
    return json.dumps(result, indent=2, default=str)


@tool
def get_service_health(service_name: str = "all", environment: str = "prod") -> str:
    """Get health overview for services based on error rates in the last hour.

    Args:
        service_name: Service name pattern, or 'all' for all services
        environment: Environment to check (default: 'prod')

    Returns:
        str: JSON with health summary including error counts and status
    """
    print(f"[Tool] get_service_health: service={service_name}, environment={environment}")

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=1)

    # Get total log counts
    total_filters = []
    if service_name.lower() != "all":
        total_filters.append(f"logGroup ~ '{service_name}'")
    if environment.lower() != "all":
        total_filters.append(f"logGroup ~ '-{environment.lower()}'")

    total_filter_str = " && ".join(total_filters) if total_filters else "true"
    total_query = f"source logs | filter {total_filter_str} | groupby logGroup | count | sort -_count | limit 20"

    total_response = make_coralogix_request(total_query, start_time, end_time, 20)
    total_logs = parse_coralogix_response(total_response)

    # Get error counts
    error_patterns = "message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception' || message ~ 'FATAL'"
    error_filters = total_filters + [f"({error_patterns})"]
    error_filter_str = " && ".join(error_filters)
    error_query = f"source logs | filter {error_filter_str} | groupby logGroup | count | sort -_count | limit 20"

    error_response = make_coralogix_request(error_query, start_time, end_time, 20)
    error_logs = parse_coralogix_response(error_response)

    # Build counts dict
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

        if total == 0:
            status = "NO_LOGS"
        elif error_rate > 10:
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

    result = {
        "environment": environment,
        "time_range": "Last 1 hour",
        "services_checked": len(health_results),
        "health_summary": health_results,
        "legend": {
            "HEALTHY": "Error rate < 5%",
            "WARNING": "Error rate 5-10%",
            "CRITICAL": "Error rate > 10%",
            "NO_LOGS": "No logs in time window",
        },
    }

    print(f"[Tool] Health check complete for {len(health_results)} services")
    return json.dumps(result, indent=2, default=str)


# =============================================================================
# AGENT
# =============================================================================


def create_coralogix_agent():
    """Create the Coralogix log analysis agent."""

    system_prompt = """You are a Log Analysis Assistant for Coralogix.
    if you cant do it or you dont have the tool let me know?? also should we do natuarl langauge to real queries??
    chat back to ask more clairifying questions about what the user wants before you use a tool.

Your role is to help developers and operators understand and troubleshoot issues using Coralogix logs.

LOG STRUCTURE (CloudWatch logs):
- logGroup: The service identifier (e.g., "/aws/lambda/mrrobot-cast-core-prod")
- message: The log message content
- timestamp: When the log was generated
- requestID: Request correlation ID (for tracing)

SERVICE NAMING PATTERNS:
- Cast services: logGroup contains "cast" (e.g., mrrobot-cast-core-prod, mrrobot-cast-quickbooks-prod)
- Environment suffix: -prod, -dev, -staging, -devopslocal

TOOLS AVAILABLE:
1. discover_services - Find what services exist (USE THIS FIRST if unsure)
2. get_recent_errors - Find errors with filtering by service/environment/scope
3. get_service_logs - Get all logs for a specific service
4. get_log_count - Get log volume counts (useful for trends)
5. search_logs - Custom DataPrime queries for advanced searches
6. get_service_health - Health overview with error rates

ENVIRONMENT FILTERING (IMPORTANT):
When users mention an environment, ALWAYS use the environment parameter:
- "cast core prod errors" → get_recent_errors(service_name="cast-core", environment="prod")
- "prod errors" → get_recent_errors(environment="prod")
- "dev cast errors" → get_recent_errors(scope="cast", environment="dev")

TOOL SELECTION:
- "What services exist?" → discover_services
- "Show me errors" → get_recent_errors
- "Errors in [service] [env]" → get_recent_errors(service_name="...", environment="...")
- "Logs for [service]" → get_service_logs
- "How many logs?" → get_log_count
- "Health check" → get_service_health
- Complex queries → search_logs

RESPONSE STYLE:
- Be concise and actionable
- Highlight errors first
- Group by service for clarity
- Suggest troubleshooting next steps
- Include error counts"""

    return Agent(
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        tools=[
            discover_services,
            get_recent_errors,
            get_service_logs,
            get_log_count,
            search_logs,
            get_service_health,
        ],
        system_prompt=system_prompt,
    )


# Create agent instance
coralogix_agent = create_coralogix_agent()


def run_coralogix_agent(prompt: str) -> str:
    """Run the agent with a given prompt."""
    if not CORALOGIX_API_KEY:
        return "Error: CORALOGIX_API_KEY environment variable not set. Please set it to your Coralogix API key."

    try:
        response = coralogix_agent(prompt)
        return str(response)
    except Exception as e:
        return f"Error running agent: {str(e)}"


if __name__ == "__main__":
    print("Testing Coralogix Agent...")
    print("-" * 50)

    if not CORALOGIX_API_KEY:
        print("WARNING: CORALOGIX_API_KEY not set")
        print("Export it with: export CORALOGIX_API_KEY='your-api-key'")
    else:
        test_prompt = "How are the Cast services doing? Any errors in prod?"
        print(f"Prompt: {test_prompt}\n")
        response = run_coralogix_agent(test_prompt)
        print(f"\nAgent Response:\n{response}")
