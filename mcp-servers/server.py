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

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import bitbucket
from tools.atlassian import (
    handle_add_user_to_group,
    handle_create_group,
    handle_delete_group,
    handle_get_directories,
    handle_grant_group_access,
    handle_list_groups,
    handle_list_users,
    handle_remove_user,
    handle_remove_user_from_group,
    handle_restore_user,
    handle_revoke_group_access,
    handle_suspend_user,
)
from tools.cloudwatch import (
    get_alarm_history,
    get_ecs_service_metrics,
    get_lambda_metrics,
    get_metric_statistics,
    list_alarms,
    list_log_groups,
    query_logs,
)
from tools.code_search import KB_ID, KNOWN_REPOS, get_file_from_bitbucket, search_knowledge_base
from tools.coralogix import (
    handle_discover_services,
    handle_get_recent_errors,
    handle_get_service_health,
    handle_get_service_logs,
    handle_search_logs,
)

# Create FastMCP server
mcp = FastMCP(
    name="mrrobot-mcp",
    instructions="MrRobot AI MCP Server - Code Search, Log Analysis, User Management",
)


# ============================================================================
# CODE SEARCH TOOLS (Bedrock Knowledge Base)
# ============================================================================


@mcp.tool()
def search_mrrobot_repos(query: str, num_results: int = 5) -> dict:
    """Search ALL 254 MrRobot Bitbucket repositories using AI semantic search.

    Use for CSP, CORS, auth, Lambda, S3, APIs, dashboard code, cast-core,
    emvio services, payment processing, or any MrRobot infrastructure code.

    Args:
        query: Natural language search query
        num_results: Number of results (default: 5, max: 10)
    """
    return search_knowledge_base(query, min(num_results, 10))


@mcp.tool()
def search_in_repo(query: str, repo_name: str, num_results: int = 5) -> dict:
    """Search within a SPECIFIC MrRobot repository.

    Args:
        query: Search query
        repo_name: Repository name (e.g., 'cast-core', 'emvio-gateway')
        num_results: Number of results
    """
    combined_query = f"{query} in {repo_name}"
    result = search_knowledge_base(combined_query, min(num_results * 3, 15))
    if "results" in result:
        filtered = [r for r in result["results"] if repo_name.lower() in r.get("repo", "").lower()]
        result["results"] = filtered[:num_results]
    result["repo_filter"] = repo_name
    return result


@mcp.tool()
def find_similar_code(code_snippet: str, num_results: int = 5) -> dict:
    """Find code similar to a given snippet across all repositories.

    Args:
        code_snippet: Code snippet to find similar patterns for
        num_results: Number of results
    """
    result = search_knowledge_base(code_snippet, min(num_results, 10))
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
def list_repos(filter: str = "") -> dict:
    """List all MrRobot repositories in the knowledge base.

    Args:
        filter: Optional filter pattern (e.g., 'cast', 'emvio')
    """
    repos = KNOWN_REPOS
    if filter:
        repos = [r for r in repos if filter.lower() in r.lower()]
    return {
        "total_indexed": 254,
        "matching_repos": repos,
        "count": len(repos),
        "filter": filter or "none",
    }


@mcp.tool()
def search_by_file_type(query: str, file_type: str, num_results: int = 5) -> dict:
    """Search for code patterns in specific file types.

    Args:
        query: Search query
        file_type: File extension or type (e.g., 'serverless.yml', '.tf')
        num_results: Number of results
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
# ATLASSIAN TOOLS (User/Group Management)
# ============================================================================


@mcp.tool()
def atlassian_get_directories() -> dict:
    """Get directories in the Atlassian organization."""
    return handle_get_directories()


@mcp.tool()
def atlassian_list_users(limit: int = 100, cursor: str = None) -> dict:
    """List users in the Atlassian organization directory.

    Args:
        limit: Max users to return
        cursor: Pagination cursor
    """
    return handle_list_users(limit, cursor)


@mcp.tool()
def atlassian_suspend_user(account_id: str) -> dict:
    """Suspend a user's access in the Atlassian directory. Use for offboarding.

    Args:
        account_id: User's Atlassian account ID
    """
    return handle_suspend_user(account_id)


@mcp.tool()
def atlassian_restore_user(account_id: str) -> dict:
    """Restore a suspended user's access.

    Args:
        account_id: User's Atlassian account ID
    """
    return handle_restore_user(account_id)


@mcp.tool()
def atlassian_remove_user(account_id: str) -> dict:
    """Completely remove a user from the Atlassian directory.

    Args:
        account_id: User's Atlassian account ID
    """
    return handle_remove_user(account_id)


@mcp.tool()
def atlassian_list_groups(limit: int = 100) -> dict:
    """List all groups in the Atlassian organization.

    Args:
        limit: Max groups to return
    """
    return handle_list_groups(limit)


@mcp.tool()
def atlassian_create_group(name: str, description: str = "") -> dict:
    """Create a new group in the Atlassian directory.

    Args:
        name: Group name
        description: Group description
    """
    return handle_create_group(name, description)


@mcp.tool()
def atlassian_delete_group(group_id: str) -> dict:
    """Delete a group from the Atlassian directory.

    Args:
        group_id: Group ID
    """
    return handle_delete_group(group_id)


@mcp.tool()
def atlassian_add_user_to_group(group_id: str, account_id: str) -> dict:
    """Add a user to an Atlassian group. Use for onboarding.

    Args:
        group_id: Group ID
        account_id: User's account ID
    """
    return handle_add_user_to_group(group_id, account_id)


@mcp.tool()
def atlassian_remove_user_from_group(group_id: str, account_id: str) -> dict:
    """Remove a user from an Atlassian group. Use for offboarding.

    Args:
        group_id: Group ID
        account_id: User's account ID
    """
    return handle_remove_user_from_group(group_id, account_id)


@mcp.tool()
def atlassian_grant_group_access(group_id: str, role: str, resource_id: str = None) -> dict:
    """Grant product access to a group via role assignment.

    Args:
        group_id: Group ID
        role: Role to grant
        resource_id: Optional resource ID
    """
    return handle_grant_group_access(group_id, role, resource_id)


@mcp.tool()
def atlassian_revoke_group_access(group_id: str, role: str, resource_id: str = None) -> dict:
    """Revoke product access from a group.

    Args:
        group_id: Group ID
        role: Role to revoke
        resource_id: Optional resource ID
    """
    return handle_revoke_group_access(group_id, role, resource_id)


# ============================================================================
# BITBUCKET TOOLS (Repository & CI/CD Management)
# ============================================================================

# Register Bitbucket tools
bitbucket.register_tools(mcp)


# ============================================================================
# CLOUDWATCH TOOLS (Observability)
# ============================================================================


@mcp.tool()
def cloudwatch_get_metrics(
    namespace: str,
    metric_name: str,
    dimensions: list = None,
    hours_back: int = 1,
) -> dict:
    """Get CloudWatch metric statistics.

    Args:
        namespace: CloudWatch namespace (e.g., 'AWS/ECS', 'AWS/Lambda', 'AWS/RDS')
        metric_name: Metric name (e.g., 'CPUUtilization', 'Invocations')
        dimensions: List of dimension dicts [{"Name": "...", "Value": "..."}]
        hours_back: Hours of data to retrieve
    """
    return get_metric_statistics(namespace, metric_name, dimensions, hours_back=hours_back)


@mcp.tool()
def cloudwatch_list_alarms(state_value: str = None, alarm_prefix: str = None) -> dict:
    """List CloudWatch alarms, optionally filtered by state.

    Args:
        state_value: Filter by state ('OK', 'ALARM', 'INSUFFICIENT_DATA')
        alarm_prefix: Filter by alarm name prefix
    """
    return list_alarms(state_value, alarm_prefix)


@mcp.tool()
def cloudwatch_get_alarm_history(alarm_name: str, hours_back: int = 24) -> dict:
    """Get state change history for a CloudWatch alarm.

    Args:
        alarm_name: Name of the alarm
        hours_back: Hours of history to retrieve
    """
    return get_alarm_history(alarm_name, hours_back)


@mcp.tool()
def cloudwatch_list_log_groups(prefix: str = None, limit: int = 50) -> dict:
    """List CloudWatch Log Groups.

    Args:
        prefix: Filter by log group name prefix (e.g., '/aws/lambda/', '/ecs/')
        limit: Maximum log groups to return
    """
    return list_log_groups(prefix, limit)


@mcp.tool()
def cloudwatch_query_logs(
    log_group: str,
    query: str = "fields @timestamp, @message | sort @timestamp desc | limit 50",
    hours_back: int = 1,
) -> dict:
    """Run a CloudWatch Logs Insights query.

    Args:
        log_group: Log group name
        query: Logs Insights query (default: last 50 messages)
        hours_back: Hours of logs to search
    """
    return query_logs(log_group, query, hours_back)


@mcp.tool()
def cloudwatch_ecs_metrics(cluster_name: str, service_name: str, hours_back: int = 1) -> dict:
    """Get ECS service CPU and memory utilization.

    Args:
        cluster_name: ECS cluster name (e.g., 'mrrobot-ai-core')
        service_name: ECS service name (e.g., 'mrrobot-mcp-server')
        hours_back: Hours of data to retrieve
    """
    return get_ecs_service_metrics(cluster_name, service_name, hours_back)


@mcp.tool()
def cloudwatch_lambda_metrics(function_name: str, hours_back: int = 1) -> dict:
    """Get Lambda function metrics (invocations, errors, duration).

    Args:
        function_name: Lambda function name
        hours_back: Hours of data to retrieve
    """
    return get_lambda_metrics(function_name, hours_back)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

VERSION = "2.2.0"
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
    mcp_http_app = mcp.streamable_http_app()
    mcp_sse_app = mcp.sse_app()

    # Create combined Starlette app with health routes + MCP
    app = Starlette(
        routes=[
            Route("/", root, methods=["GET"]),
            Route("/health", health, methods=["GET"]),
            # Mount MCP apps
            Mount("/mcp", app=mcp_http_app),
            Mount("/sse", app=mcp_sse_app),
        ]
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
    args = parser.parse_args()

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
