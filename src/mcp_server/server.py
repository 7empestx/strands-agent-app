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

VERSION = "2.4.0"  # Bumped for Confluence tools
START_TIME = datetime.now(timezone.utc)


def get_tool_count() -> int:
    """Get the number of registered tools."""
    try:
        return len(mcp._tool_manager._tools)
    except Exception:
        return 30  # Fallback estimate


def run_http_server(host: str, port: int):
    """Run MCP server with HTTP transport and health endpoints."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

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
                },
                "tools": get_tool_count(),
            }
        )

    # Get the MCP ASGI apps
    # Note: sse_app() creates routes at /sse and /messages/ internally
    # We mount at root so clients can connect directly to /sse
    # See: https://github.com/modelcontextprotocol/python-sdk/issues/412
    mcp_http_app = mcp.streamable_http_app()
    mcp_sse_app = mcp.sse_app()

    # Create combined Starlette app with health routes + MCP
    # Mount SSE app at root (it has its own /sse and /messages/ routes)
    # Mount MCP app at /mcp
    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            # Mount MCP HTTP transport at /mcp
            Mount("/mcp", app=mcp_http_app),
            # Mount SSE app at root (provides /sse and /messages/ routes)
            Mount("/", app=mcp_sse_app),
        ],
    )

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
    slack_bot = None
    if args.slack:
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
