"""
Coralogix Log Analysis Agent
Uses Strands SDK with Claude Sonnet on Amazon Bedrock
"""

import json
import os
from datetime import datetime, timedelta

import boto3
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

# =============================================================================
# DATAPRIME QUERY KNOWLEDGE STORE
# =============================================================================
# This knowledge store contains DataPrime query patterns and examples that
# the AI uses to generate queries dynamically from natural language.

DATAPRIME_KNOWLEDGE = {
    "syntax": {
        "description": "DataPrime is Coralogix's query language for searching logs",
        "structure": "source logs | filter <conditions> | <aggregations> | limit <n>",
        "operators": {
            "~": "Contains/regex match (e.g., message ~ 'error')",
            "==": "Exact match (e.g., severity == 'ERROR')",
            "!=": "Not equal",
            "&&": "Logical AND",
            "||": "Logical OR",
            ">": "Greater than (for numbers/dates)",
            "<": "Less than",
            ">=": "Greater than or equal",
            "<=": "Less than or equal",
        },
        "functions": {
            "count": "Count results (groupby field | count)",
            "distinct": "Get unique values (distinct fieldName)",
            "groupby": "Group results by field",
            "sort": "Sort results (sort -field for descending)",
            "limit": "Limit number of results",
        },
    },
    "field_mappings": {
        "message": "The log message content",
        "logGroup": "Service/application identifier (e.g., '/aws/lambda/mrrobot-cast-core-prod')",
        "timestamp": "Log timestamp",
        "requestID": "Request correlation ID for tracing",
        "severity": "Log level (INFO, WARN, ERROR, etc.)",
    },
    "environment_patterns": {
        "prod": "-prod",
        "production": "-prod",
        "dev": "-dev",
        "development": "-dev",
        "staging": "-staging",
        "stage": "-staging",
        "local": "-devopslocal",
    },
    "examples": [
        {
            "intent": "Find all errors",
            "query": "source logs | filter message ~ 'ERROR' || message ~ 'Error' || message ~ 'Exception' | limit 100",
        },
        {
            "intent": "Find errors in a specific service",
            "query": "source logs | filter logGroup ~ 'cast-core' && (message ~ 'ERROR' || message ~ 'Exception') | limit 100",
        },
        {
            "intent": "Find errors in production environment",
            "query": "source logs | filter logGroup ~ '-prod' && (message ~ 'ERROR' || message ~ 'Exception') | limit 100",
        },
        {
            "intent": "Count logs by service",
            "query": "source logs | groupby logGroup | count | sort -_count | limit 50",
        },
        {
            "intent": "Find timeout errors",
            "query": "source logs | filter message ~ 'timeout' || message ~ 'Timeout' || message ~ 'TIMEOUT' | limit 100",
        },
        {
            "intent": "Find authentication failures",
            "query": "source logs | filter message ~ 'auth' && (message ~ 'fail' || message ~ 'denied' || message ~ 'unauthorized') | limit 100",
        },
        {
            "intent": "Find logs with specific request ID",
            "query": "source logs | filter requestID == 'abc-123-def' | limit 100",
        },
        {
            "intent": "Find database connection errors",
            "query": "source logs | filter message ~ 'database' || message ~ 'connection' || message ~ 'ECONNREFUSED' | limit 100",
        },
        {
            "intent": "Find payment processing issues",
            "query": "source logs | filter logGroup ~ 'payment' && (message ~ 'fail' || message ~ 'decline' || message ~ 'error') | limit 100",
        },
        {
            "intent": "Get unique services/log groups",
            "query": "source logs | distinct logGroup | limit 100",
        },
        {
            "intent": "Find 5xx HTTP errors",
            "query": "source logs | filter message ~ '500' || message ~ '502' || message ~ '503' || message ~ '504' | limit 100",
        },
        {
            "intent": "Find memory or OOM issues",
            "query": "source logs | filter message ~ 'memory' || message ~ 'OOM' || message ~ 'heap' || message ~ 'OutOfMemory' | limit 100",
        },
        {
            "intent": "Find slow queries or latency issues",
            "query": "source logs | filter message ~ 'slow' || message ~ 'latency' || message ~ 'duration' | limit 100",
        },
        {
            "intent": "Find CVV or sensitive card data in logs",
            "query": "source logs | filter message ~ 'cvv' || message ~ 'cvc' || message ~ 'security_code' | limit 100",
        },
        {
            "intent": "Find Lambda cold starts",
            "query": "source logs | filter message ~ 'cold start' || message ~ 'Init Duration' | limit 100",
        },
    ],
}


def generate_dataprime_query(
    natural_language_request: str,
    service_filter: str = None,
    environment: str = None,
    limit: int = 100,
) -> str:
    """
    Generate a DataPrime query from natural language using the knowledge store.
    Uses Claude via Bedrock to translate the request into a valid query.
    """
    # Build context from knowledge store
    examples_text = "\n".join(
        [f"- Intent: {ex['intent']}\n  Query: {ex['query']}" for ex in DATAPRIME_KNOWLEDGE["examples"]]
    )

    operators_text = "\n".join([f"- {op}: {desc}" for op, desc in DATAPRIME_KNOWLEDGE["syntax"]["operators"].items()])

    functions_text = "\n".join([f"- {fn}: {desc}" for fn, desc in DATAPRIME_KNOWLEDGE["syntax"]["functions"].items()])

    fields_text = "\n".join([f"- {field}: {desc}" for field, desc in DATAPRIME_KNOWLEDGE["field_mappings"].items()])

    # Build additional filters
    additional_filters = []
    if service_filter:
        additional_filters.append(f"Filter to service matching: {service_filter}")
    if environment:
        env_pattern = DATAPRIME_KNOWLEDGE["environment_patterns"].get(environment.lower(), f"-{environment}")
        additional_filters.append(f"Filter to environment: {environment} (pattern: {env_pattern})")

    additional_context = "\n".join(additional_filters) if additional_filters else "No additional filters"

    prompt = f"""Generate a DataPrime query for Coralogix based on this request.

USER REQUEST: {natural_language_request}

ADDITIONAL FILTERS:
{additional_context}

DATAPRIME SYNTAX:
Structure: {DATAPRIME_KNOWLEDGE["syntax"]["structure"]}

OPERATORS:
{operators_text}

FUNCTIONS:
{functions_text}

AVAILABLE FIELDS:
{fields_text}

EXAMPLE QUERIES:
{examples_text}

RULES:
1. Always start with "source logs"
2. Use filter for conditions
3. Use ~ for contains/regex matching (case sensitive - include variations)
4. Use && for AND, || for OR
5. Always end with "| limit {limit}"
6. For environment filtering, use logGroup ~ '-prod' or '-dev' etc.
7. Return ONLY the query, no explanation

QUERY:"""

    try:
        # Use Bedrock to generate the query
        bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        response = bedrock.invoke_model(
            modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )
        result = json.loads(response["body"].read())
        query = result["content"][0]["text"].strip()

        # Clean up the query (remove any markdown formatting)
        if query.startswith("```"):
            query = query.split("\n", 1)[1] if "\n" in query else query[3:]
        if query.endswith("```"):
            query = query.rsplit("```", 1)[0]
        query = query.strip()

        return query
    except Exception as e:
        # Fallback to a basic query if generation fails
        print(f"[Query Generator] Failed to generate query: {e}")
        base_query = f"source logs | filter message ~ '{natural_language_request.split()[0]}'"
        if service_filter:
            base_query += f" && logGroup ~ '{service_filter}'"
        if environment:
            env_pattern = DATAPRIME_KNOWLEDGE["environment_patterns"].get(environment.lower(), f"-{environment}")
            base_query += f" && logGroup ~ '{env_pattern}'"
        base_query += f" | limit {limit}"
        return base_query


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
def smart_log_search(
    request: str,
    service_name: str = None,
    environment: str = None,
    hours_back: int = 4,
    limit: int = 100,
) -> str:
    """AI-powered log search - describe what you're looking for in natural language.

    This tool uses AI to generate the appropriate DataPrime query based on your
    natural language description. No need to know query syntax!

    Args:
        request: Natural language description of what to search for
                 (e.g., "find timeout errors", "show authentication failures",
                 "find slow database queries", "look for payment declines")
        service_name: Optional service filter (e.g., "cast-core", "payment")
        environment: Optional environment filter ("prod", "dev", "staging")
        hours_back: How many hours back to search (default: 4)
        limit: Maximum number of results (default: 100)

    Returns:
        str: JSON with generated query and matching log entries
    """
    print(f"[Tool] smart_log_search: request='{request}', service={service_name}, env={environment}")

    # Generate the query using AI
    generated_query = generate_dataprime_query(
        natural_language_request=request,
        service_filter=service_name,
        environment=environment,
        limit=limit,
    )

    print(f"[Tool] Generated query: {generated_query}")

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    response = make_coralogix_request(generated_query, start_time, end_time, limit)
    logs = parse_coralogix_response(response)

    # Group logs by service for better readability
    logs_by_service = {}
    for log in logs:
        log_group = log.get("logGroup", "unknown")
        parts = log_group.split("/")
        service = parts[-1] if parts else log_group
        if service not in logs_by_service:
            logs_by_service[service] = []
        logs_by_service[service].append(log)

    result = {
        "original_request": request,
        "generated_query": generated_query,
        "filters_applied": {
            "service": service_name or "all",
            "environment": environment or "all",
        },
        "time_range": f"Last {hours_back} hour(s)",
        "total_results": len(logs),
        "services_found": len(logs_by_service),
        "logs_by_service": {svc: {"count": len(items), "logs": items[:20]} for svc, items in logs_by_service.items()},
    }

    print(f"[Tool] Found {len(logs)} log entries across {len(logs_by_service)} services")
    return json.dumps(result, indent=2, default=str)


@tool
def get_query_examples() -> str:
    """Get examples of log search queries from the knowledge store.

    Use this to understand what kinds of searches are available and
    to get inspiration for your own queries.

    Returns:
        str: JSON with example queries and their intents
    """
    print("[Tool] get_query_examples")

    result = {
        "description": "Example DataPrime queries for common log searches",
        "syntax_reference": DATAPRIME_KNOWLEDGE["syntax"],
        "examples": DATAPRIME_KNOWLEDGE["examples"],
        "available_fields": DATAPRIME_KNOWLEDGE["field_mappings"],
        "environment_patterns": DATAPRIME_KNOWLEDGE["environment_patterns"],
        "tip": "Use smart_log_search with natural language instead of writing queries manually!",
    }

    return json.dumps(result, indent=2, default=str)


# =============================================================================
# PCI DATA DETECTION PATTERNS
# Based on mrrobot-pii-npm/src/pii/pci.js and pci-file-scanner
# =============================================================================

# CVV/CVC regex patterns from mrrobot-pii-npm
# Matches: cvv, cvv2, cvc, ccv, ssc, security code, security_code, securityCode
# With various delimiters and 3-4 digit values
CVV_REGEX_PATTERNS = [
    # Main CVV pattern with field name prefix (from mrrobot-pii-npm)
    r'(?:credit_card_|creditCard)?(?:cvv|cvv2|cvc|ccv|ssc|security[_ ]?code|securityCode)[\s"\'\\=:]+(\d{3,4})',
    # JSON format: "cvv": "123" or "cvv": 123
    r'"(?:cvv|cvv2|cvc|ccv|ssc|security_code|securityCode)":\s*"?(\d{3,4})"?',
    # Key=value format: cvv=123
    r"(?:cvv|cvv2|cvc|ccv|ssc|security_code|securityCode)=(\d{3,4})",
    # Python/JS object: 'cvv': '123'
    r"'(?:cvv|cvv2|cvc|ccv|ssc|security_code|securityCode)':\s*'?(\d{3,4})'?",
]

# PAN (Card Number) regex patterns from pci-file-scanner
# Matches major card brands with various separators
PAN_REGEX_PATTERNS = [
    # Visa: 4xxx xxxx xxxx xxxx
    r"\b4\d{3}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b",
    # Mastercard: 5[1-5]xx or 2[2-7]xx
    r"\b(?:5[1-5]\d{2}|2[2-7]\d{2})[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b",
    # Amex: 3[47]xx xxxxxx xxxxx
    r"\b3[47]\d{2}[\s.-]?\d{6}[\s.-]?\d{5}\b",
    # Discover: 6011, 65, 644-649
    r"\b(?:6011|65\d{2}|64[4-9]\d)[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b",
]

# Terms to search for in Coralogix (used in DataPrime query)
CVV_SEARCH_TERMS = [
    "cvv",
    "cvc",
    "cvv2",
    "ccv",
    "ssc",
    "security_code",
    "securityCode",
]

# Known false positive patterns to ignore (from mrrobot-pii-npm cvvCheckAlwaysIgnore)
CVV_FALSE_POSITIVES = [
    "cvv is required",
    "cvv must be",
    "cvv validation",
    "cvv error",
    "invalid cvv",
    "cvv field",
    "cvv_required",
    "cvv_validation",
]


def detect_pci_data(text: str) -> dict:
    """
    Detect PCI data (CVV and PAN) in text using patterns from mrrobot-pii-npm.
    Returns detection results with redacted values.

    Based on: mrrobot-pii-npm/src/pii/pci.js and pci-file-scanner/classes/scanner.py
    """
    import re

    result = {
        "has_cvv": False,
        "has_pan": False,
        "cvv_count": 0,
        "pan_count": 0,
        "redacted_text": text,
        "is_false_positive": False,
    }

    # Check for false positives first
    text_lower = text.lower()
    for fp in CVV_FALSE_POSITIVES:
        if fp in text_lower:
            result["is_false_positive"] = True

    # Detect CVV patterns
    for pattern in CVV_REGEX_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            result["has_cvv"] = True
            result["cvv_count"] += len(matches)
            # Redact CVV values
            result["redacted_text"] = re.sub(
                pattern,
                lambda m: m.group(0).replace(m.group(1), "[CVV-REDACTED]") if m.groups() else "[CVV-REDACTED]",
                result["redacted_text"],
                flags=re.IGNORECASE,
            )

    # Detect PAN patterns (with Luhn validation would be ideal, but regex first)
    for pattern in PAN_REGEX_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            result["has_pan"] = True
            result["pan_count"] += len(matches)
            # Redact PAN values (show only last 4)
            result["redacted_text"] = re.sub(
                pattern,
                lambda m: "[PAN-REDACTED-" + m.group(0)[-4:] + "]",
                result["redacted_text"],
            )

    return result


@tool
def find_cvv_in_logs(
    service_name: str = "all",
    hours_back: int = 24,
    environment: str = "all",
    limit: int = 100,
    include_pan: bool = True,
) -> str:
    """Search for CVV/CVC/PAN patterns in logs - PCI-DSS compliance check.

    Uses detection patterns from mrrobot-pii-npm and pci-file-scanner.
    CVVs and unmasked PANs should NEVER appear in logs.

    Args:
        service_name: Service name pattern, or 'all' for all services
        hours_back: How many hours back to search (default: 24)
        environment: Environment filter - 'all', 'prod', 'dev', etc.
        limit: Maximum number of results (default: 100)
        include_pan: Also search for card numbers/PANs (default: True)

    Returns:
        str: JSON with any log entries containing PCI data (values are redacted)
    """
    print(
        f"[Tool] find_cvv_in_logs: service={service_name}, hours_back={hours_back}, "
        f"environment={environment}, include_pan={include_pan}"
    )

    # Build the search pattern for Coralogix
    pattern_conditions = " || ".join([f"message ~ '{term}'" for term in CVV_SEARCH_TERMS])

    # Add PAN patterns if requested (search for card number prefixes)
    if include_pan:
        pan_search_terms = ["4[0-9]{3}", "5[1-5][0-9]{2}", "3[47][0-9]{2}", "6011"]
        pan_conditions = " || ".join([f"message ~ '{term}'" for term in pan_search_terms])
        pattern_conditions = f"({pattern_conditions}) || ({pan_conditions})"

    # Build filters
    filters = [f"({pattern_conditions})"]

    if service_name.lower() != "all":
        filters.append(f"logGroup ~ '{service_name}'")

    if environment.lower() != "all":
        filters.append(f"logGroup ~ '-{environment.lower()}'")

    filter_str = " && ".join(filters)
    query = f"source logs | filter {filter_str} | limit {limit}"

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    response = make_coralogix_request(query, start_time, end_time, limit)
    logs = parse_coralogix_response(response)

    # Process logs with PCI detection
    findings = []
    cvv_findings = 0
    pan_findings = 0
    false_positives = 0

    for log in logs:
        message = log.get("message", "")
        log_group = log.get("logGroup", "unknown")

        # Use the detection function based on mrrobot-pii-npm patterns
        detection = detect_pci_data(message)

        if detection["has_cvv"] or detection["has_pan"]:
            if detection["is_false_positive"]:
                false_positives += 1
                continue

            parts = log_group.split("/")
            service = parts[-1] if parts else log_group

            if detection["has_cvv"]:
                cvv_findings += detection["cvv_count"]
            if detection["has_pan"]:
                pan_findings += detection["pan_count"]

            redacted_preview = detection["redacted_text"]
            if len(redacted_preview) > 500:
                redacted_preview = redacted_preview[:500] + "..."

            findings.append(
                {
                    "service": service,
                    "log_group": log_group,
                    "timestamp": log.get("timestamp"),
                    "has_cvv": detection["has_cvv"],
                    "has_pan": detection["has_pan"],
                    "cvv_count": detection["cvv_count"],
                    "pan_count": detection["pan_count"],
                    "message_preview": redacted_preview,
                    "request_id": log.get("requestID", ""),
                }
            )

    # Group by service
    by_service = {}
    for finding in findings:
        svc = finding["service"]
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append(finding)

    # Determine severity
    if cvv_findings > 0:
        severity = "CRITICAL"  # CVV in logs is always critical
    elif pan_findings > 0:
        severity = "HIGH"  # Unmasked PAN is high severity
    else:
        severity = "OK"

    result = {
        "severity": severity,
        "pci_compliance_check": "CVV and PAN in logs",
        "detection_source": "Based on mrrobot-pii-npm and pci-file-scanner patterns",
        "time_range": f"Last {hours_back} hour(s)",
        "environment": environment,
        "summary": {
            "total_findings": len(findings),
            "cvv_instances": cvv_findings,
            "pan_instances": pan_findings,
            "false_positives_filtered": false_positives,
            "services_affected": len(by_service),
        },
        "findings_by_service": {
            svc: {
                "count": len(items),
                "cvv_count": sum(i["cvv_count"] for i in items),
                "pan_count": sum(i["pan_count"] for i in items),
                "samples": items[:5],
            }
            for svc, items in by_service.items()
        },
        "recommendation": (
            "CRITICAL: CVV data found in logs! CVVs must NEVER be logged per PCI-DSS. "
            "Immediately investigate and remediate the logging code."
            if cvv_findings > 0
            else (
                "HIGH: Unmasked PAN data found in logs. Card numbers should be masked. "
                "Review logging to ensure only last 4 digits are shown."
                if pan_findings > 0
                else "No PCI data detected in logs - compliant!"
            )
        ),
        "reference": "Detection patterns from: mrrobot-pii-npm/src/pii/pci.js, pci-file-scanner/classes/scanner.py",
    }

    print(
        f"[Tool] PCI scan complete: {len(findings)} findings "
        f"(CVV: {cvv_findings}, PAN: {pan_findings}) across {len(by_service)} services"
    )
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
Ask clarifying questions before using tools if the user's request is ambiguous.

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
1. smart_log_search - AI-POWERED search: describe what you want in natural language! (PREFERRED)
2. discover_services - Find what services exist (USE THIS FIRST if unsure)
3. get_recent_errors - Find errors with filtering by service/environment/scope
4. get_service_logs - Get all logs for a specific service
5. get_log_count - Get log volume counts (useful for trends)
6. get_service_health - Health overview with error rates
7. find_cvv_in_logs - PCI-DSS compliance check for CVV/CVC/PAN data in logs (uses mrrobot-pii-npm patterns)
8. get_query_examples - See example queries from the knowledge store
9. search_logs - Execute raw DataPrime queries (advanced users only)

TOOL SELECTION (PREFER smart_log_search for flexibility):
- "Find timeout errors in prod" → smart_log_search(request="timeout errors", environment="prod")
- "Show me authentication failures" → smart_log_search(request="authentication failures")
- "Any database connection issues?" → smart_log_search(request="database connection errors")
- "What services exist?" → discover_services
- "Health check" → get_service_health
- "Check for CVV in logs" → find_cvv_in_logs (PCI compliance)
- "How do I write queries?" → get_query_examples

ENVIRONMENT FILTERING (IMPORTANT):
When users mention an environment, ALWAYS use the environment parameter:
- "prod errors" → smart_log_search(request="errors", environment="prod")
- "dev cast errors" → smart_log_search(request="errors", service_name="cast", environment="dev")

RESPONSE STYLE:
- Be concise and actionable
- Highlight errors first
- Group by service for clarity
- Suggest troubleshooting next steps
- Include error counts
- Show the generated query so users can learn"""

    return Agent(
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        tools=[
            smart_log_search,
            discover_services,
            get_recent_errors,
            get_service_logs,
            get_log_count,
            search_logs,
            get_service_health,
            find_cvv_in_logs,
            get_query_examples,
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
