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
"""

import argparse
import os
import sys

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
from tools.bedrock_kb import KB_ID, KNOWN_REPOS, get_file_from_bitbucket, search_knowledge_base
from tools.coralogix import (
    handle_discover_services,
    handle_get_recent_errors,
    handle_get_service_health,
    handle_get_service_logs,
    handle_search_logs,
)

# Create FastMCP server
mcp = FastMCP(
    "mrrobot-mcp",
    version="2.0.0",
    description="MrRobot AI MCP Server - Code Search, Log Analysis, User Management",
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
# MAIN ENTRY POINT
# ============================================================================


def main():
    parser = argparse.ArgumentParser(description="MrRobot MCP Server")
    parser.add_argument("--http", "--sse", action="store_true", help="Run as HTTP server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP server")
    args = parser.parse_args()

    print(f"[MCP] MrRobot MCP Server v2.0.0")
    print(f"[MCP] Tools registered: {len(mcp._tool_manager._tools)}")

    if args.http:
        # Run with Streamable HTTP transport
        print(f"[MCP] Starting HTTP server on http://{args.host}:{args.port}")
        print(f"[MCP] Endpoint: http://{args.host}:{args.port}/mcp")

        # Use FastMCP's built-in HTTP server
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
        )
    else:
        # Run with stdio transport
        print("[MCP] Starting in stdio mode...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
