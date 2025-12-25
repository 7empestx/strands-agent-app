"""Error pattern recognition for Clippy.

Maps common error messages to investigation hints and recommended actions.
Helps Clippy provide more targeted troubleshooting guidance.
"""

# Common error patterns with investigation hints
ERROR_PATTERNS = {
    # Connection errors
    "ECONNREFUSED": {
        "category": "connection",
        "likely_cause": "Target service is down or unreachable",
        "check_first": [
            "Target service logs and status",
            "Network connectivity / security groups",
            "DNS resolution",
        ],
        "tools": ["search_logs", "get_pipeline_status"],
        "questions": ["What service is it trying to connect to?", "Did that service have a recent deploy?"],
    },
    "ETIMEDOUT": {
        "category": "connection",
        "likely_cause": "Network timeout - service not responding in time",
        "check_first": [
            "Target service response times in logs",
            "Network latency / VPN issues",
            "Load balancer health checks",
        ],
        "tools": ["search_logs", "aws_cli"],
        "questions": ["Is this happening to all requests or just some?"],
    },
    "ENOTFOUND": {
        "category": "dns",
        "likely_cause": "DNS resolution failure - hostname not found",
        "check_first": ["DNS configuration", "Environment variables with hostnames", "VPC DNS settings"],
        "tools": ["search_code", "aws_cli"],
        "questions": ["What hostname is it trying to resolve?"],
    },
    # HTTP errors
    "504": {
        "category": "timeout",
        "likely_cause": "Gateway timeout - backend took too long to respond",
        "check_first": [
            "Lambda/service duration in logs",
            "Database query times",
            "Downstream service response times",
        ],
        "tools": ["search_logs", "get_pipeline_status"],
        "questions": ["Is this a specific endpoint or all endpoints?", "Any recent deploys?"],
    },
    "502": {
        "category": "gateway",
        "likely_cause": "Bad gateway - backend returned invalid response or crashed",
        "check_first": ["Backend service logs for crashes", "Memory issues", "Recent deploys"],
        "tools": ["search_logs", "get_pipeline_status"],
        "questions": ["Is the backend service running?"],
    },
    "503": {
        "category": "availability",
        "likely_cause": "Service unavailable - overloaded or in maintenance",
        "check_first": ["Service health/status", "Load balancer target health", "Scaling events"],
        "tools": ["search_logs", "aws_cli"],
        "questions": ["Is this a specific service or multiple?"],
    },
    "401": {
        "category": "auth",
        "likely_cause": "Unauthorized - invalid or missing authentication",
        "check_first": ["Token/API key validity", "Auth service logs", "Recent auth service deploys"],
        "tools": ["search_logs", "get_pipeline_status"],
        "questions": ["Is this for a specific user or all users?", "When did this start?"],
    },
    "403": {
        "category": "auth",
        "likely_cause": "Forbidden - authenticated but not authorized",
        "check_first": ["Permission/role configuration", "IAM policies", "API Gateway authorizers"],
        "tools": ["search_logs", "search_code"],
        "questions": ["What resource is being accessed?", "What role/permission is expected?"],
    },
    "429": {
        "category": "rate_limit",
        "likely_cause": "Too many requests - rate limited",
        "check_first": ["Request volume in logs", "Rate limit configuration", "Retry logic"],
        "tools": ["search_logs", "search_code"],
        "questions": ["Is this from a specific client or integration?"],
    },
    # Application errors
    "CORS": {
        "category": "cors",
        "likely_cause": "Cross-origin request blocked - missing CORS headers",
        "check_first": ["API Gateway CORS config", "Lambda response headers", "CloudFront behavior settings"],
        "tools": ["search_code", "search_logs"],
        "questions": ["What origin is making the request?", "What endpoint is affected?"],
    },
    "OOM": {
        "category": "memory",
        "likely_cause": "Out of memory - process exceeded memory limit",
        "check_first": ["Lambda memory configuration", "Memory usage patterns", "Memory leaks"],
        "tools": ["search_logs", "aws_cli"],
        "questions": ["Is this Lambda or ECS?", "When did memory usage spike?"],
    },
    "OutOfMemory": {
        "category": "memory",
        "likely_cause": "Out of memory - process exceeded memory limit",
        "check_first": ["Container/Lambda memory limits", "Recent code changes", "Data volume processed"],
        "tools": ["search_logs", "get_pipeline_status"],
        "questions": ["What triggered the memory spike?"],
    },
    "cold start": {
        "category": "performance",
        "likely_cause": "Lambda cold start - first invocation after idle",
        "check_first": ["Provisioned concurrency settings", "Lambda init duration", "Package size"],
        "tools": ["search_logs", "aws_cli"],
        "questions": ["Is this happening frequently or just occasionally?"],
    },
    # Database errors
    "deadlock": {
        "category": "database",
        "likely_cause": "Database deadlock - concurrent transactions conflicting",
        "check_first": ["Database logs", "Transaction patterns", "Lock wait timeout settings"],
        "tools": ["search_logs"],
        "questions": ["What tables/queries are involved?"],
    },
    "connection pool": {
        "category": "database",
        "likely_cause": "Connection pool exhausted - too many concurrent connections",
        "check_first": ["Connection pool settings", "Connection count in logs", "Long-running queries"],
        "tools": ["search_logs", "search_code"],
        "questions": ["How many concurrent connections are configured?"],
    },
    # SSL/TLS errors
    "certificate": {
        "category": "ssl",
        "likely_cause": "SSL certificate issue - expired, invalid, or mismatch",
        "check_first": ["Certificate expiration dates", "Domain name match", "CA trust chain"],
        "tools": ["aws_cli"],
        "questions": ["What domain is the certificate for?", "When does it expire?"],
    },
    "UNABLE_TO_VERIFY_LEAF_SIGNATURE": {
        "category": "ssl",
        "likely_cause": "SSL certificate chain incomplete or untrusted",
        "check_first": ["Intermediate certificates", "CA bundle configuration"],
        "tools": ["search_code"],
        "questions": ["Is this a custom/internal CA?"],
    },
}


def get_pattern_hints(error_message: str) -> dict | None:
    """Get investigation hints for an error message.

    Args:
        error_message: Error message or log text to analyze

    Returns:
        dict with pattern info, hints, and recommendations, or None if no match
    """
    if not error_message:
        return None

    error_lower = error_message.lower()

    # Check for pattern matches
    for pattern, hints in ERROR_PATTERNS.items():
        if pattern.lower() in error_lower:
            return {
                "matched_pattern": pattern,
                **hints,
            }

    return None


def get_investigation_context(error_message: str) -> str:
    """Get investigation context string to add to prompt.

    Args:
        error_message: Error message from user query

    Returns:
        Context string with investigation hints, or empty string if no match
    """
    hints = get_pattern_hints(error_message)

    if not hints:
        return ""

    context_parts = [
        f"\n\n---\n*Error Pattern Detected: {hints['matched_pattern']}*",
        f"Category: {hints['category']}",
        f"Likely cause: {hints['likely_cause']}",
        "Check first:",
    ]

    for item in hints.get("check_first", []):
        context_parts.append(f"  - {item}")

    if hints.get("questions"):
        context_parts.append("Questions to ask:")
        for q in hints["questions"]:
            context_parts.append(f"  - {q}")

    return "\n".join(context_parts)


def categorize_error(error_message: str) -> str:
    """Categorize an error for storage and analysis.

    Args:
        error_message: Error message text

    Returns:
        Category string (e.g., 'connection', 'timeout', 'auth')
    """
    hints = get_pattern_hints(error_message)
    return hints.get("category", "unknown") if hints else "unknown"
