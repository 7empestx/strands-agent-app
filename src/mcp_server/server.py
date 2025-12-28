#!/usr/bin/env python3
"""
MrRobot MCP Server - Unified MCP server using official Anthropic SDK.

Uses FastMCP for clean, decorator-based tool definitions.

Local usage:  python server.py
Remote usage: python server.py --http --port 8080

Tools available:
- Code Search (Bedrock Knowledge Base)
- Coralogix Log Analysis
- Atlassian Admin (User/Group Management)
- Bitbucket (PRs, Pipelines, Repos)
"""

import argparse
import os
import sys
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Add project root to path for imports (go up from src/mcp_server to project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.lib import bitbucket

# Atlassian Admin API tools disabled - requires separate admin API key
# from src.lib.atlassian import (
#     handle_add_user_to_group,
#     handle_create_group,
#     handle_delete_group,
#     handle_get_directories,
#     handle_grant_group_access,
#     handle_list_groups,
#     handle_list_users,
#     handle_remove_user,
#     handle_remove_user_from_group,
#     handle_restore_user,
#     handle_revoke_group_access,
#     handle_suspend_user,
# )
# CloudWatch removed - use Coralogix for all log analysis
from src.lib.code_search import KB_ID, get_file_from_bitbucket, search_knowledge_base
from src.lib.config_loader import get_service_registry, lookup_service
from src.lib.confluence import handle_get_page, handle_get_page_by_title
from src.lib.confluence import handle_get_recent_updates as confluence_get_recent_updates
from src.lib.confluence import handle_list_spaces
from src.lib.confluence import handle_search as confluence_search
from src.lib.confluence import handle_search_by_label as confluence_search_by_label
from src.lib.coralogix import (
    handle_discover_services,
    handle_get_recent_errors,
    handle_get_service_health,
    handle_get_service_logs,
    handle_search_logs,
)
from src.lib.jira import get_issue as jira_get_issue
from src.lib.jira import get_issue_comments as jira_get_issue_comments
from src.lib.jira import get_issues_by_label as jira_get_issues_by_label
from src.lib.jira import get_open_cve_issues as jira_get_open_cve_issues
from src.lib.jira import handle_search_jira
from src.lib.pagerduty import extract_service_name_from_incident, handle_active_incidents, handle_incident_details
from src.mcp_server.alert_enhancer import enhance_alert

# Create FastMCP server with custom domain allowed for DNS rebinding protection
# See: https://github.com/modelcontextprotocol/python-sdk/issues/1798
mcp = FastMCP(
    name="mrrobot-mcp",
    instructions="MrRobot AI MCP Server - Code Search, Log Analysis, User Management",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            "mcp.mrrobot.dev",
            "mcp.mrrobot.dev:*",
        ],
        allowed_origins=[
            "http://localhost:*",
            "https://localhost:*",
            "http://127.0.0.1:*",
            "https://mcp.mrrobot.dev",
            "https://mcp.mrrobot.dev:*",
        ],
    ),
)


# ============================================================================
# CODE SEARCH TOOLS (Bedrock Knowledge Base)
# ============================================================================


@mcp.tool()
def search_mrrobot_repos(query: str, num_results: int = 10) -> dict:
    """Search ALL 254 MrRobot Bitbucket repositories using AI semantic search.

    Use for CSP, CORS, auth, Lambda, S3, APIs, dashboard code, cast-core,
    emvio services, payment processing, or any MrRobot infrastructure code.

    Returns results with file_type, relevance rating (high/medium/low/weak), and more context.

    Args:
        query: Natural language search query
        num_results: Number of results (default: 10, max: 25)
    """
    return search_knowledge_base(query, min(num_results, 25))


@mcp.tool()
def search_in_repo(query: str, repo_name: str, num_results: int = 10) -> dict:
    """Search within a SPECIFIC MrRobot repository.

    Args:
        query: Search query
        repo_name: Repository name (e.g., 'cast-core', 'emvio-gateway')
        num_results: Number of results (default: 10)
    """
    combined_query = f"{query} in {repo_name}"
    result = search_knowledge_base(combined_query, min(num_results * 2, 25))
    if "results" in result:
        filtered = [r for r in result["results"] if repo_name.lower() in r.get("repo", "").lower()]
        result["results"] = filtered[:num_results]
    result["repo_filter"] = repo_name
    return result


@mcp.tool()
def find_similar_code(code_snippet: str, num_results: int = 10) -> dict:
    """Find code similar to a given snippet across all repositories.

    Args:
        code_snippet: Code snippet to find similar patterns for
        num_results: Number of results (default: 10)
    """
    result = search_knowledge_base(code_snippet, min(num_results, 25))
    result["search_type"] = "similar_code"
    return result


@mcp.tool()
def get_kb_info() -> dict:
    """Get information about the MrRobot code knowledge base."""
    return {
        "knowledge_base_id": KB_ID,
        "stats": {
            "repositories": 254,
            "documents_indexed": 17169,
            "embedding_model": "amazon.titan-embed-text-v2:0",
        },
        "tips": [
            "Use natural language queries - semantic search understands intent",
            "Be specific: 'JWT validation in gateway' beats 'authentication'",
        ],
    }


@mcp.tool()
def get_file_content(repo: str, file_path: str, branch: str = "master") -> dict:
    """Fetch full file content from Bitbucket.

    Args:
        repo: Repository name
        file_path: Path to file
        branch: Branch name (default: master)
    """
    return get_file_from_bitbucket(repo, file_path, branch)


@mcp.tool()
def get_service_info(service_name: str) -> dict:
    """Look up a MrRobot service by name or alias.

    Returns service type (frontend/backend/library), tech stack, description,
    and troubleshooting suggestions. Searches 129 known services.

    Args:
        service_name: Service name, key, or alias (e.g., 'cast', 'dashboard', 'emvio-auth-service')
    """
    service_info = lookup_service(service_name)

    if service_info:
        service_type = service_info.get("type", "unknown")
        return {
            "found": True,
            "key": service_info.get("key"),
            "full_name": service_info.get("full_name"),
            "type": service_type,
            "tech_stack": service_info.get("tech_stack", []),
            "description": service_info.get("description", ""),
            "aliases": service_info.get("aliases", []),
            "repo": service_info.get("repo", service_info.get("full_name")),
            "suggestion": (
                "Frontend app - check deploys and browser console for API errors."
                if service_type == "frontend"
                else (
                    "Backend service - check logs first, then recent deploys."
                    if service_type == "backend"
                    else (
                        "Library/tool - used by other services, check dependents."
                        if service_type in ("library", "tool")
                        else "Check both logs and deploys."
                    )
                )
            ),
        }
    else:
        return {
            "found": False,
            "service_name": service_name,
            "message": f"Service '{service_name}' not found in registry.",
            "suggestion": "Try a different name or use search_mrrobot_repos to find it.",
            "total_known_services": len(get_service_registry()),
        }


@mcp.tool()
def list_all_services(service_type: str = None) -> dict:
    """List all known MrRobot services, optionally filtered by type.

    Args:
        service_type: Optional filter - 'frontend', 'backend', 'library', 'tool', or None for all
    """
    registry = get_service_registry()

    services = []
    for key, info in registry.items():
        svc_type = info.get("type", "unknown")
        if service_type is None or svc_type == service_type:
            services.append(
                {
                    "key": key,
                    "full_name": info.get("full_name"),
                    "type": svc_type,
                    "description": info.get("description", "")[:100],
                }
            )

    # Sort by type then key
    services.sort(key=lambda x: (x["type"], x["key"]))

    return {
        "total": len(services),
        "filter": service_type,
        "services": services,
    }


# Note: list_repos is available via the mrrobot-code-kb MCP server
# which queries the actual S3/OpenSearch index of 254 repos.


@mcp.tool()
def search_by_file_type(query: str, file_type: str, num_results: int = 10) -> dict:
    """Search for code patterns in specific file types.

    Args:
        query: Search query
        file_type: File extension or type (e.g., 'serverless.yml', '.tf')
        num_results: Number of results (default: 10)
    """
    enhanced_query = f"file:{file_type} {query}"
    result = search_knowledge_base(enhanced_query, num_results)
    if "results" in result:
        result["results"] = [r for r in result["results"] if file_type.lower() in r.get("file", "").lower()]
    result["file_type_filter"] = file_type
    return result


# ============================================================================
# CORALOGIX TOOLS (Log Analysis)
# ============================================================================


@mcp.tool()
def coralogix_discover_services(hours_back: int = 1, limit: int = 50) -> dict:
    """Discover available log groups/services in Coralogix.

    Args:
        hours_back: How many hours back to search
        limit: Maximum services to return
    """
    return handle_discover_services(hours_back, limit)


@mcp.tool()
def coralogix_get_recent_errors(
    service_name: str = "all",
    hours_back: int = 4,
    limit: int = 100,
    environment: str = "all",
) -> dict:
    """Get recent errors from Coralogix logs, grouped by service.

    Args:
        service_name: Service name or 'all'
        hours_back: Hours to search back
        limit: Max results
        environment: 'prod', 'dev', 'staging', or 'all'
    """
    return handle_get_recent_errors(service_name, hours_back, limit, environment)


@mcp.tool()
def coralogix_get_service_logs(
    service_name: str,
    hours_back: int = 1,
    error_only: bool = False,
    limit: int = 50,
    environment: str = "all",
) -> dict:
    """Get logs for a specific service from Coralogix.

    Args:
        service_name: Service name pattern
        hours_back: Hours to search back
        error_only: Only return error logs
        limit: Max results
        environment: Environment filter
    """
    return handle_get_service_logs(service_name, hours_back, error_only, limit, environment)


@mcp.tool()
def coralogix_search_logs(query: str, hours_back: int = 4, limit: int = 100) -> dict:
    """Execute a custom DataPrime query on Coralogix logs.

    Args:
        query: DataPrime query (e.g., "source logs | filter message ~ 'error'")
        hours_back: Hours to search back
        limit: Max results
    """
    return handle_search_logs(query, hours_back, limit)


@mcp.tool()
def coralogix_get_service_health(service_name: str = "all", environment: str = "prod") -> dict:
    """Get health overview for services based on error rates.

    Args:
        service_name: Service name or 'all'
        environment: Environment (default: prod)
    """
    return handle_get_service_health(service_name, environment)


# ============================================================================
# ============================================================================
# ATLASSIAN TOOLS (User/Group Management) - DISABLED
# Requires separate admin API key from admin.atlassian.com
# Uncomment when admin API key is configured
# ============================================================================

# @mcp.tool()
# def atlassian_get_directories() -> dict:
#     """Get directories in the Atlassian organization."""
#     return handle_get_directories()
#
# @mcp.tool()
# def atlassian_list_users(limit: int = 100, cursor: str = None) -> dict:
#     """List users in the Atlassian organization directory."""
#     return handle_list_users(limit, cursor)
#
# @mcp.tool()
# def atlassian_suspend_user(account_id: str) -> dict:
#     """Suspend a user's access in the Atlassian directory."""
#     return handle_suspend_user(account_id)
#
# @mcp.tool()
# def atlassian_restore_user(account_id: str) -> dict:
#     """Restore a suspended user's access."""
#     return handle_restore_user(account_id)
#
# @mcp.tool()
# def atlassian_remove_user(account_id: str) -> dict:
#     """Completely remove a user from the Atlassian directory."""
#     return handle_remove_user(account_id)
#
# @mcp.tool()
# def atlassian_list_groups(limit: int = 100) -> dict:
#     """List all groups in the Atlassian organization."""
#     return handle_list_groups(limit)
#
# @mcp.tool()
# def atlassian_create_group(name: str, description: str = "") -> dict:
#     """Create a new group in the Atlassian directory."""
#     return handle_create_group(name, description)
#
# @mcp.tool()
# def atlassian_delete_group(group_id: str) -> dict:
#     """Delete a group from the Atlassian directory."""
#     return handle_delete_group(group_id)
#
# @mcp.tool()
# def atlassian_add_user_to_group(group_id: str, account_id: str) -> dict:
#     """Add a user to an Atlassian group."""
#     return handle_add_user_to_group(group_id, account_id)
#
# @mcp.tool()
# def atlassian_remove_user_from_group(group_id: str, account_id: str) -> dict:
#     """Remove a user from an Atlassian group."""
#     return handle_remove_user_from_group(group_id, account_id)
#
# @mcp.tool()
# def atlassian_grant_group_access(group_id: str, role: str, resource_id: str = None) -> dict:
#     """Grant product access to a group via role assignment."""
#     return handle_grant_group_access(group_id, role, resource_id)
#
# @mcp.tool()
# def atlassian_revoke_group_access(group_id: str, role: str, resource_id: str = None) -> dict:
#     """Revoke product access from a group."""
#     return handle_revoke_group_access(group_id, role, resource_id)


# ============================================================================
# BITBUCKET TOOLS (Repository & CI/CD Management)
# ============================================================================

# Register Bitbucket tools
bitbucket.register_tools(mcp)


# ============================================================================
# JIRA TOOLS
# ============================================================================


@mcp.tool()
def jira_search(query: str, max_results: int = 20) -> dict:
    """Search Jira tickets using natural language or JQL.

    Examples:
    - "CVE tickets" - finds issues with CVE label
    - "open bugs" - finds open bug tickets
    - "my tickets" - finds your assigned tickets
    - "DEVOPS-123" - gets specific ticket details
    - "labels = CVE AND status != Done" - raw JQL query

    Args:
        query: Natural language search or JQL query
        max_results: Maximum results to return (default: 20)
    """
    return handle_search_jira(query, max_results)


@mcp.tool()
def jira_get_ticket(issue_key: str) -> dict:
    """Get detailed information about a specific Jira ticket.

    Args:
        issue_key: The ticket key (e.g., 'DEVOPS-123', 'SEC-456')
    """
    return jira_get_issue(issue_key)


@mcp.tool()
def jira_get_comments(issue_key: str, max_results: int = 10) -> dict:
    """Get comments on a Jira ticket.

    Args:
        issue_key: The ticket key (e.g., 'DEVOPS-123')
        max_results: Maximum comments to return
    """
    return jira_get_issue_comments(issue_key, max_results)


@mcp.tool()
def jira_cve_tickets(max_results: int = 50) -> dict:
    """Get open CVE/security vulnerability tickets.

    Returns tickets labeled with CVE, security, or vulnerability
    that are not yet resolved.
    """
    return jira_get_open_cve_issues(max_results)


@mcp.tool()
def jira_tickets_by_label(label: str, status: str = None, max_results: int = 20) -> dict:
    """Get Jira tickets with a specific label.

    Args:
        label: Label to search for (e.g., 'CVE', 'security', 'urgent')
        status: Optional status filter (e.g., 'Open', 'In Progress', 'Done')
        max_results: Maximum results to return
    """
    return jira_get_issues_by_label(label, status, max_results)


# ============================================================================
# CONFLUENCE TOOLS
# ============================================================================


@mcp.tool()
def confluence_search_docs(query: str, space_key: str = None, limit: int = 10) -> dict:
    """Search Confluence documentation using natural language.

    Use for finding HR policies, runbooks, architecture docs, onboarding guides,
    team processes, and company documentation.

    Examples:
    - "PTO policy" - finds paid time off documentation
    - "onboarding checklist" - finds new hire guides
    - "deployment runbook" - finds ops procedures
    - "payment processing architecture" - finds technical docs

    Args:
        query: Natural language search query
        space_key: Limit to specific space (e.g., 'HR', 'DEV', 'OPS') - optional
        limit: Maximum results (default: 10)
    """
    return confluence_search(query, space_key, limit)


@mcp.tool()
def confluence_get_page(page_id: str, include_body: bool = True) -> dict:
    """Get a specific Confluence page by its ID.

    Args:
        page_id: Confluence page ID
        include_body: Whether to include full page content (default: True)
    """
    return handle_get_page(page_id, include_body)


@mcp.tool()
def confluence_get_page_by_title(title: str, space_key: str) -> dict:
    """Get a Confluence page by its exact title.

    Args:
        title: Exact page title
        space_key: Space key where the page lives (e.g., 'HR', 'DEV')
    """
    return handle_get_page_by_title(title, space_key)


@mcp.tool()
def confluence_list_spaces(limit: int = 50) -> dict:
    """List all available Confluence spaces.

    Returns space keys, names, and descriptions.

    Args:
        limit: Maximum spaces to return (default: 50)
    """
    return handle_list_spaces(limit)


@mcp.tool()
def confluence_recent_updates(space_key: str = None, limit: int = 15) -> dict:
    """Get recently updated Confluence pages.

    Useful for seeing what documentation has changed recently.

    Args:
        space_key: Limit to specific space (optional)
        limit: Maximum results (default: 15)
    """
    return confluence_get_recent_updates(space_key, limit)


@mcp.tool()
def confluence_pages_by_label(label: str, space_key: str = None, limit: int = 20) -> dict:
    """Find Confluence pages with a specific label.

    Common labels: 'runbook', 'architecture', 'policy', 'onboarding', 'how-to'

    Args:
        label: Label to search for
        space_key: Limit to specific space (optional)
        limit: Maximum results (default: 20)
    """
    return confluence_search_by_label(label, space_key, limit)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

VERSION = "2.5.0"  # Bumped for Dashboard API
START_TIME = datetime.now(timezone.utc)


# ============================================================================
# AI Analysis Helper Functions (for Dashboard API)
# ============================================================================


def _generate_incident_analysis(incident: dict, service_name: str) -> dict:
    """Generate a quick AI analysis for an incident (used in list view).

    This is a lightweight analysis based on incident title patterns.
    For full analysis with code search, use _generate_detailed_analysis.
    """
    title = incident.get("title", "").lower()
    urgency = incident.get("urgency", "low")

    # Pattern-based quick analysis
    summary = ""
    suggested_fix = ""
    code_location = None

    # CSP/CORS errors
    if "csp" in title or "cors" in title or "cross-origin" in title:
        summary = (
            "Content Security Policy or CORS configuration issue. Browser blocking requests due to missing headers."
        )
        suggested_fix = "Check CORS configuration in API Gateway or S3 bucket policy. Add appropriate AllowedOrigins."
        code_location = f"https://bitbucket.org/mrrobot-labs/{service_name}/src/master/"

    # Timeout errors
    elif "timeout" in title or "504" in title or "gateway timeout" in title:
        summary = "Request timeout - backend taking too long to respond. Could be slow database queries or external API delays."
        suggested_fix = (
            "Check for slow database queries, increase timeout limits, or add pagination for large data sets."
        )

    # Memory/CPU alerts
    elif "memory" in title or "cpu" in title or "utilization" in title:
        summary = "Resource utilization alert. Service may need scaling or has a memory/CPU leak."
        suggested_fix = (
            "Review recent deployments for memory leaks. Consider horizontal scaling or container resource limits."
        )

    # Database/latency issues
    elif "latency" in title or "slow" in title or "database" in title:
        summary = "Performance degradation detected. Slow queries or increased load affecting response times."
        suggested_fix = "Check database indexes, review recent query changes, consider adding caching layer."

    # 5xx errors
    elif "500" in title or "502" in title or "503" in title or "5xx" in title:
        summary = "Server error indicating application or infrastructure issue."
        suggested_fix = "Check application logs for stack traces. Review recent deployments."

    # Authentication errors
    elif "auth" in title or "401" in title or "403" in title or "token" in title:
        summary = "Authentication or authorization failure. Token may be expired or permissions misconfigured."
        suggested_fix = "Check API token validity and permissions. Review IAM policies if AWS-related."

    # Default
    else:
        summary = f"Alert on {service_name}: {incident.get('title', 'Unknown issue')}"
        suggested_fix = "Check application logs and recent deployments for this service."

    return {
        "summary": summary,
        "suggested_fix": suggested_fix,
        "code_location": code_location,
        "service_identified": service_name,
        "urgency_assessment": "immediate" if urgency == "high" else "monitor",
    }


def _generate_detailed_analysis(incident: dict, service_name: str, code_results: dict, logs: dict) -> dict:
    """Generate a detailed AI analysis with code search results and logs."""
    # Start with basic analysis
    basic = _generate_incident_analysis(incident, service_name)

    # Enhance with code search results
    related_files = []
    if code_results and "results" in code_results:
        for result in code_results.get("results", [])[:3]:
            related_files.append(
                {
                    "file": result.get("file", ""),
                    "repo": result.get("repo", ""),
                    "relevance": result.get("relevance", ""),
                    "url": result.get("bitbucket_url", ""),
                }
            )

    # Extract error patterns from logs
    error_patterns = []
    log_list = logs.get("logs", logs.get("errors", []))
    if isinstance(log_list, list):
        for log_entry in log_list[:5]:
            if isinstance(log_entry, dict):
                msg = log_entry.get("message", log_entry.get("error", ""))
                if msg:
                    error_patterns.append(msg[:200])
            elif isinstance(log_entry, str):
                error_patterns.append(log_entry[:200])

    return {
        **basic,
        "related_files": related_files,
        "error_patterns": error_patterns,
        "logs_found": len(log_list) if isinstance(log_list, list) else 0,
    }


def _generate_code_fix_analysis(incident: dict, service_name: str, code_results: dict) -> dict:
    """Generate detailed code fix suggestions based on knowledge base search."""
    basic = _generate_incident_analysis(incident, service_name)

    # Build suggested fixes based on code search results
    suggested_fixes = [basic.get("suggested_fix", "")]

    affected_code = None
    if code_results and "results" in code_results:
        results = code_results.get("results", [])
        if results:
            top_result = results[0]
            affected_code = {
                "file": f"{top_result.get('repo', '')}/{top_result.get('file', '')}",
                "url": top_result.get("bitbucket_url", ""),
                "snippet": top_result.get("content", "")[:500],
                "relevance": top_result.get("relevance", ""),
            }

            # Add more specific fixes based on file type
            file_ext = top_result.get("file_type", "")
            if file_ext in ["js", "ts", "jsx", "tsx"]:
                suggested_fixes.append("Review error handling in async functions")
                suggested_fixes.append("Check for unhandled promise rejections")
            elif file_ext in ["py"]:
                suggested_fixes.append("Review exception handling and logging")
                suggested_fixes.append("Check for connection pool exhaustion")
            elif file_ext in ["yml", "yaml"]:
                suggested_fixes.append("Review infrastructure configuration")
                suggested_fixes.append("Check environment-specific settings")

    # Find similar past issues (placeholder - would query historical data)
    similar_issues = []

    return {
        "summary": basic.get("summary", ""),
        "root_cause": f"Likely issue in {service_name} - {basic.get('summary', '')}",
        "affected_code": affected_code,
        "suggested_fixes": list(dict.fromkeys(suggested_fixes)),  # Remove duplicates
        "similar_issues": similar_issues,
        "service": service_name,
    }


def get_tool_count() -> int:
    """Get the number of registered tools."""
    try:
        return len(mcp._tool_manager._tools)
    except Exception:
        return 30  # Fallback estimate


def run_http_server(host: str, port: int):
    """Run MCP server with HTTP transport and health endpoints."""
    import asyncio

    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route, WebSocketRoute

    # Import auth and chatbot modules
    from src.mcp_server.auth import (
        AuthMiddleware,
        handle_callback,
        handle_login,
        handle_logout,
        handle_user_info,
        is_auth_configured,
    )
    from src.mcp_server.chatbot import handle_chat_websocket

    # Health check endpoint
    async def health(request):
        now = datetime.now(timezone.utc)
        uptime = (now - START_TIME).total_seconds()
        return JSONResponse(
            {
                "status": "healthy",
                "version": VERSION,
                "tools": get_tool_count(),
                "uptime_seconds": round(uptime, 1),
                "timestamp": now.isoformat().replace("+00:00", "Z"),
            }
        )

    # Root endpoint - same as health for simplicity
    async def root(request):
        return JSONResponse(
            {
                "service": "MrRobot MCP Server",
                "version": VERSION,
                "status": "running",
                "endpoints": {
                    "/": "This info",
                    "/health": "Health check",
                    "/mcp": "MCP protocol (streamable-http)",
                    "/sse": "MCP protocol (SSE)",
                    "/api/alerts": "Dashboard alerts API",
                },
                "tools": get_tool_count(),
            }
        )

    # ========================================================================
    # Dashboard REST API endpoints
    # ========================================================================

    async def api_alerts_active(request):
        """Get active PagerDuty incidents with AI analysis."""
        try:
            # Run PagerDuty call in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            incidents_data = await loop.run_in_executor(None, handle_active_incidents)

            if "error" in incidents_data:
                return JSONResponse({"error": incidents_data["error"]}, status_code=500)

            # For each incident, generate AI analysis
            incidents_with_analysis = []
            for incident in incidents_data.get("incidents", []):
                # Extract service name for code search
                service_name = extract_service_name_from_incident(incident)

                # Generate quick AI analysis based on incident title
                analysis = await loop.run_in_executor(
                    None,
                    lambda i=incident, s=service_name: _generate_incident_analysis(i, s),
                )

                incidents_with_analysis.append(
                    {
                        "incident": incident,
                        "analysis": analysis,
                    }
                )

            return JSONResponse(
                {
                    "total": len(incidents_with_analysis),
                    "incidents": incidents_with_analysis,
                }
            )
        except Exception as e:
            print(f"[API] Error in /api/alerts/active: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    async def api_alert_details(request):
        """Get detailed incident info with full analysis."""
        incident_id = request.path_params["incident_id"]
        try:
            loop = asyncio.get_event_loop()
            incident = await loop.run_in_executor(None, lambda: handle_incident_details(incident_id))

            if "error" in incident:
                return JSONResponse({"error": incident["error"]}, status_code=404)

            # Get service name and run full analysis
            service_name = extract_service_name_from_incident(incident)

            # Search for related code
            code_results = await loop.run_in_executor(
                None,
                lambda: search_knowledge_base(f"{incident.get('title', '')} {service_name}", num_results=5),
            )

            # Get recent errors from Coralogix
            logs = await loop.run_in_executor(
                None,
                lambda: handle_get_recent_errors(service_name, hours_back=4, limit=20),
            )

            # Generate detailed analysis
            analysis = await loop.run_in_executor(
                None,
                lambda: _generate_detailed_analysis(incident, service_name, code_results, logs),
            )

            return JSONResponse(
                {
                    "incident": incident,
                    "analysis": analysis,
                    "related_code": code_results.get("results", [])[:3],
                    "recent_logs": logs.get("logs", logs.get("errors", []))[:10],
                }
            )
        except Exception as e:
            print(f"[API] Error in /api/alerts/{incident_id}: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    async def api_analyze_incident(request):
        """Trigger AI analysis for an incident (POST)."""
        incident_id = request.path_params["incident_id"]
        try:
            body = await request.json()
            include_code_fix = body.get("include_code_fix", True)

            loop = asyncio.get_event_loop()
            incident = await loop.run_in_executor(None, lambda: handle_incident_details(incident_id))

            if "error" in incident:
                return JSONResponse({"error": incident["error"]}, status_code=404)

            service_name = extract_service_name_from_incident(incident)

            # Search codebase for relevant code
            code_results = None
            if include_code_fix:
                code_results = await loop.run_in_executor(
                    None,
                    lambda: search_knowledge_base(f"{incident.get('title', '')} error fix", num_results=10),
                )

            # Generate AI analysis with code fix suggestions
            analysis = await loop.run_in_executor(
                None,
                lambda: _generate_code_fix_analysis(incident, service_name, code_results),
            )

            return JSONResponse(
                {
                    "incident_id": incident_id,
                    "analysis": analysis,
                }
            )
        except Exception as e:
            print(f"[API] Error in POST /api/alerts/{incident_id}/analyze: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    async def api_enhance_alert(request):
        """
        Enhance a CloudWatch alarm with AI-powered analysis.

        POST /api/enhance-alert
        Body: {
            "alarm_name": "CAST [PROD] - EWriteBackPayment",
            "service": "mrrobot-cast-core",
            "error_code": "EWriteBackPayment",  # optional
            "severity": "Critical",              # optional
            "reason": "Threshold Crossed...",    # optional
            "log_group": "/aws/lambda/...",      # optional
            "timestamp": "2025-12-26T18:00:00Z", # optional
            "environment": "prod"                # optional
        }

        Returns AI analysis with root cause, affected code, suggested fixes, etc.
        """
        try:
            body = await request.json()

            # Validate required fields
            if not body.get("service") and not body.get("alarm_name"):
                return JSONResponse(
                    {"status": "error", "error": "Missing required field: 'service' or 'alarm_name'"},
                    status_code=400,
                )

            # Run enhancement in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: enhance_alert(body))

            return JSONResponse(result)

        except Exception as e:
            print(f"[API] Error in POST /api/enhance-alert: {e}")
            return JSONResponse(
                {"status": "error", "error": str(e)},
                status_code=500,
            )

    # Get the MCP ASGI apps
    # Note: sse_app() creates routes at /sse and /messages/ internally
    # We mount at root so clients can connect directly to /sse
    # See: https://github.com/modelcontextprotocol/python-sdk/issues/412
    mcp_http_app = mcp.streamable_http_app()
    mcp_sse_app = mcp.sse_app()

    # CORS middleware for dashboard
    allowed_origins = [
        "https://ai-agent.mrrobot.dev",
        "https://ai-agent.nex.io",
        "https://mcp.mrrobot.dev",
        "https://mcp.nex.io",
        "http://localhost:3000",
        "http://localhost:5173",  # Vite dev server
    ]
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    # Add auth middleware if configured
    if is_auth_configured():
        middleware.append(Middleware(AuthMiddleware))
        print("[MCP] Azure AD authentication enabled")
    else:
        print("[MCP] Azure AD not configured - running without authentication")

    # Check if dashboard static files exist (built React app)
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web-dashboard", "dist")
    has_dashboard = os.path.exists(dashboard_dir)
    if has_dashboard:
        from starlette.staticfiles import StaticFiles

        print(f"[MCP] Dashboard static files found at {dashboard_dir}")
    else:
        print(f"[MCP] Dashboard not found at {dashboard_dir} - API-only mode")

    # Build routes list
    routes = [
        Route("/health", health, methods=["GET"]),
        # Auth routes
        Route("/auth/login", handle_login, methods=["GET"]),
        Route("/auth/callback", handle_callback, methods=["GET"]),
        Route("/auth/logout", handle_logout, methods=["GET", "POST"]),
        Route("/api/user", handle_user_info, methods=["GET"]),
        # Chatbot WebSocket
        WebSocketRoute("/api/chat", handle_chat_websocket),
        # Dashboard REST API routes
        Route("/api/alerts/active", api_alerts_active, methods=["GET"]),
        Route("/api/alerts/{incident_id}", api_alert_details, methods=["GET"]),
        Route("/api/alerts/{incident_id}/analyze", api_analyze_incident, methods=["POST"]),
        # Alert enhancement API (for external services like cloudwatchAlarmNotifier)
        Route("/api/enhance-alert", api_enhance_alert, methods=["POST"]),
        # Mount MCP protocol endpoints
        Mount("/mcp", app=mcp_http_app),
        Mount("/sse", app=mcp_sse_app),
    ]

    # Serve dashboard at root if available, otherwise mount SSE at root
    if has_dashboard:
        routes.append(Mount("/", app=StaticFiles(directory=dashboard_dir, html=True), name="dashboard"))
    else:
        routes.append(Mount("/", app=mcp_sse_app))

    # Create combined Starlette app
    app = Starlette(routes=routes, middleware=middleware)

    print(f"[MCP] MrRobot MCP Server v{VERSION}")
    print(f"[MCP] Tools registered: {get_tool_count()}")
    print(f"[MCP] Starting HTTP server on http://{host}:{port}")
    print(f"[MCP] Endpoints:")
    print(f"[MCP]   - Health: http://{host}:{port}/health")
    print(f"[MCP]   - MCP:    http://{host}:{port}/mcp")
    print(f"[MCP]   - SSE:    http://{host}:{port}/sse")

    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    parser = argparse.ArgumentParser(description="MrRobot MCP Server")
    parser.add_argument("--http", "--sse", action="store_true", help="Run as HTTP server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP server")
    parser.add_argument("--slack", action="store_true", help="Also start Slack bot")
    args = parser.parse_args()

    # Optionally start Slack bot in background
    # Check ENABLE_SLACK env var (set by CDK - only 'true' in dev)
    enable_slack = os.environ.get("ENABLE_SLACK", "true").lower() == "true"
    slack_bot = None
    if args.slack and enable_slack:
        try:
            from slack_bot import SlackBot

            slack_bot = SlackBot()
            if slack_bot.is_configured():
                slack_bot.start(blocking=False)
                print("[Slack] Bot started in background")
            else:
                print("[Slack] Tokens not configured, skipping bot")
        except ImportError as e:
            print(f"[Slack] Could not import slack_bot: {e}")
        except Exception as e:
            print(f"[Slack] Error starting bot: {e}")
    elif args.slack and not enable_slack:
        print("[Slack] Bot disabled via ENABLE_SLACK env var")

    if args.http:
        run_http_server(args.host, args.port)
    else:
        # Run with stdio transport (for local development)
        print(f"[MCP] MrRobot MCP Server v{VERSION}")
        print(f"[MCP] Tools registered: {get_tool_count()}")
        print("[MCP] Starting in stdio mode...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
