"""Conversation memory for Clippy.

Stores investigation results and solutions for future reference.
Helps Clippy learn from past issues to provide better responses.
"""

import json
import time
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

# S3 bucket for memory storage
MEMORY_BUCKET = "mrrobot-code-kb-dev-720154970215"
MEMORY_PREFIX = "clippy-memory/"

# In-memory cache with TTL
_memory_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_s3_client():
    """Get S3 client."""
    return boto3.client("s3", region_name="us-east-1")


def store_investigation(
    service: str,
    environment: str,
    issue_type: str,
    findings: str,
    resolution: str = None,
    tools_used: list = None,
    error_patterns: list = None,
):
    """Store an investigation result for future reference.

    Args:
        service: Service name (e.g., 'cast-core')
        environment: Environment (prod/staging/dev)
        issue_type: Type of issue (e.g., '504_timeout', 'ECONNREFUSED', 'deployment_failure')
        findings: Summary of what was found
        resolution: How it was resolved (if known)
        tools_used: List of tools that helped
        error_patterns: Specific error messages/patterns found
    """
    try:
        s3 = _get_s3_client()

        investigation = {
            "service": service.lower(),
            "environment": environment.lower(),
            "issue_type": issue_type,
            "findings": findings[:2000],
            "resolution": resolution[:1000] if resolution else None,
            "tools_used": tools_used or [],
            "error_patterns": error_patterns or [],
            "timestamp": datetime.utcnow().isoformat(),
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
        }

        # Store by service and date for easy retrieval
        date_str = datetime.utcnow().strftime("%Y/%m/%d")
        ts = int(time.time() * 1000)
        key = f"{MEMORY_PREFIX}investigations/{service.lower()}/{date_str}/{ts}.json"

        s3.put_object(
            Bucket=MEMORY_BUCKET,
            Key=key,
            Body=json.dumps(investigation, indent=2),
            ContentType="application/json",
        )

        print(f"[Memory] Stored investigation for {service}/{environment}: {issue_type}")
        return True

    except Exception as e:
        print(f"[Memory] Error storing investigation: {e}")
        return False


def get_recent_investigations(
    service: str,
    environment: str = None,
    days: int = 7,
    limit: int = 5,
) -> list:
    """Get recent investigations for a service.

    Args:
        service: Service name to look up
        environment: Optional environment filter
        days: How many days back to search
        limit: Max investigations to return

    Returns:
        List of investigation dicts, most recent first
    """
    cache_key = f"investigations:{service}:{environment}:{days}"

    # Check cache
    if cache_key in _memory_cache:
        cached, cached_time = _memory_cache[cache_key]
        if time.time() - cached_time < CACHE_TTL_SECONDS:
            return cached

    try:
        s3 = _get_s3_client()
        investigations = []

        # Search past N days
        for i in range(days):
            date = datetime.utcnow() - timedelta(days=i)
            date_str = date.strftime("%Y/%m/%d")
            prefix = f"{MEMORY_PREFIX}investigations/{service.lower()}/{date_str}/"

            try:
                response = s3.list_objects_v2(Bucket=MEMORY_BUCKET, Prefix=prefix)
                for obj in response.get("Contents", []):
                    content = s3.get_object(Bucket=MEMORY_BUCKET, Key=obj["Key"])
                    inv = json.loads(content["Body"].read())

                    # Filter by environment if specified
                    if environment and inv.get("environment") != environment.lower():
                        continue

                    investigations.append(inv)

            except ClientError:
                continue

        # Sort by timestamp, most recent first
        investigations.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        result = investigations[:limit]

        # Cache result
        _memory_cache[cache_key] = (result, time.time())

        return result

    except Exception as e:
        print(f"[Memory] Error getting investigations: {e}")
        return []


def find_similar_issues(
    error_pattern: str,
    service: str = None,
    days: int = 30,
) -> list:
    """Find past issues with similar error patterns.

    Args:
        error_pattern: Error message or pattern to search for
        service: Optional service filter
        days: How many days back to search

    Returns:
        List of matching investigations with similarity info
    """
    try:
        s3 = _get_s3_client()
        matches = []

        # Normalize search pattern
        search_terms = error_pattern.lower().split()

        # Build prefix based on service filter
        if service:
            prefix = f"{MEMORY_PREFIX}investigations/{service.lower()}/"
        else:
            prefix = f"{MEMORY_PREFIX}investigations/"

        # List all investigations (this could be optimized with a search index)
        paginator = s3.get_paginator("list_objects_v2")
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        for page in paginator.paginate(Bucket=MEMORY_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                try:
                    content = s3.get_object(Bucket=MEMORY_BUCKET, Key=obj["Key"])
                    inv = json.loads(content["Body"].read())

                    # Check if within date range
                    inv_date = datetime.fromisoformat(inv.get("timestamp", "2000-01-01"))
                    if inv_date < cutoff_date:
                        continue

                    # Check for pattern matches
                    inv_text = (
                        f"{inv.get('findings', '')} {inv.get('issue_type', '')} "
                        f"{' '.join(inv.get('error_patterns', []))}"
                    ).lower()

                    # Simple matching - count how many search terms appear
                    match_count = sum(1 for term in search_terms if term in inv_text)

                    if match_count > 0:
                        inv["match_score"] = match_count / len(search_terms)
                        matches.append(inv)

                except Exception:
                    continue

        # Sort by match score
        matches.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return matches[:10]

    except Exception as e:
        print(f"[Memory] Error finding similar issues: {e}")
        return []


def get_service_issue_history(service: str, days: int = 90) -> dict:
    """Get issue history summary for a service.

    Args:
        service: Service name
        days: How many days back to analyze

    Returns:
        dict with issue counts by type, common patterns, etc.
    """
    investigations = get_recent_investigations(service, days=days, limit=100)

    if not investigations:
        return {"service": service, "total_issues": 0}

    # Aggregate by issue type
    issue_counts = {}
    environments = {}
    all_patterns = []

    for inv in investigations:
        issue_type = inv.get("issue_type", "unknown")
        issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

        env = inv.get("environment", "unknown")
        environments[env] = environments.get(env, 0) + 1

        all_patterns.extend(inv.get("error_patterns", []))

    # Find most common patterns
    pattern_counts = {}
    for p in all_patterns:
        pattern_counts[p] = pattern_counts.get(p, 0) + 1

    return {
        "service": service,
        "period_days": days,
        "total_issues": len(investigations),
        "issues_by_type": dict(sorted(issue_counts.items(), key=lambda x: -x[1])),
        "issues_by_environment": environments,
        "common_patterns": dict(sorted(pattern_counts.items(), key=lambda x: -x[1])[:10]),
        "most_recent": investigations[0] if investigations else None,
    }


def add_context_from_memory(message: str, service: str = None, environment: str = None) -> str:
    """Add relevant memory context to a message before sending to Claude.

    Args:
        message: Original user message
        service: Detected service name (if any)
        environment: Detected environment (if any)

    Returns:
        Message with memory context appended (if relevant history found)
    """
    if not service:
        return message

    # Look for recent similar issues
    recent = get_recent_investigations(service, environment, days=7, limit=3)

    if not recent:
        return message

    # Build context string
    context_parts = ["\n\n---\n*Relevant history for this service:*"]

    for inv in recent:
        date = inv.get("date", "")
        issue_type = inv.get("issue_type", "issue")
        findings = inv.get("findings", "")[:200]
        resolution = inv.get("resolution", "")

        context_parts.append(f"- [{date}] {issue_type}: {findings}")
        if resolution:
            context_parts.append(f"  Resolution: {resolution[:150]}")

    context = "\n".join(context_parts)

    print(f"[Memory] Added context from {len(recent)} past investigations")
    return message + context
