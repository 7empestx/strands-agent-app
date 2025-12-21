"""
Bitbucket Agent - Repository and CI/CD management.

This agent uses the same underlying functions as the MCP server tools,
ensuring consistency between direct MCP access (Cursor) and agent access (Streamlit).
"""

import sys
from pathlib import Path

from strands import Agent, tool
from strands.models import BedrockModel

# Add project root to path for imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

# Import the underlying Bitbucket API functions from lib
# ruff: noqa: E402
from src.lib.bitbucket import get_commit_info as _get_commit  # noqa: E402
from src.lib.bitbucket import get_pipeline_status as _get_pipelines
from src.lib.bitbucket import get_repository_info as _get_repo
from src.lib.bitbucket import list_branches as _list_branches
from src.lib.bitbucket import list_pull_requests as _list_prs
from src.lib.bitbucket import list_repositories as _list_repos

# ============================================================================
# STRANDS TOOL WRAPPERS
# ============================================================================


@tool
def list_pull_requests(repo_slug: str = "", state: str = "OPEN", limit: int = 20) -> str:
    """List pull requests from Bitbucket.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-dashboard-app'). Empty = all repos
        state: PR state - OPEN, MERGED, DECLINED, or ALL
        limit: Maximum number of PRs to return
    """
    result = _list_prs(repo_slug, state, limit)
    if "error" in result:
        return f"Error: {result['error']}"

    prs = result.get("pull_requests", [])
    if not prs:
        return f"No {state} pull requests found"

    lines = [f"Pull Requests ({state}) - {len(prs)} found:"]
    for pr in prs:
        lines.append(f"  [{pr['repo']}] #{pr['id']}: {pr['title']}")
        lines.append(f"      Author: {pr['author']} | Created: {pr['created']}")

    return "\n".join(lines)


@tool
def get_pipeline_status(repo_slug: str, limit: int = 5) -> str:
    """Get recent pipeline/build status for a repository.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-payment-service')
        limit: Number of recent pipelines to return
    """
    result = _get_pipelines(repo_slug, limit)
    if "error" in result:
        return f"Error: {result['error']}"

    pipelines = result.get("pipelines", [])
    if not pipelines:
        return f"No pipelines found for {repo_slug}"

    lines = [f"Recent pipelines for {repo_slug}:"]
    for pipe in pipelines:
        status = pipe["result"]
        emoji = {"SUCCESSFUL": "OK", "FAILED": "FAIL", "RUNNING": "RUN"}.get(status, status)
        lines.append(f"  #{pipe['build_number']} [{emoji}] {pipe['branch']} - {pipe['created']}")

    return "\n".join(lines)


@tool
def get_repository_info(repo_slug: str) -> str:
    """Get detailed information about a repository.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-dashboard-app')
    """
    result = _get_repo(repo_slug)
    if "error" in result:
        return f"Error: {result['error']}"

    lines = [
        f"Repository: {result['name']}",
        f"  Full Name: {result['full_name']}",
        f"  Description: {result['description']}",
        f"  Language: {result['language']}",
        f"  Created: {result['created']}",
        f"  Updated: {result['updated']}",
        f"  Main Branch: {result['main_branch']}",
        f"  Private: {result['is_private']}",
        f"  URL: {result['url']}",
    ]
    return "\n".join(lines)


@tool
def list_repositories(limit: int = 50) -> str:
    """List all repositories in the workspace.

    Args:
        limit: Maximum number of repos to return
    """
    result = _list_repos(limit)
    if "error" in result:
        return f"Error: {result['error']}"

    repos = result.get("repositories", [])
    if not repos:
        return "No repositories found"

    lines = [f"Repositories in {result['workspace']} ({len(repos)}):"]
    for repo in repos:
        lines.append(f"  {repo['slug']} ({repo['language']}) - updated {repo['updated']}")

    return "\n".join(lines)


@tool
def get_commit_info(repo_slug: str, commit_hash: str) -> str:
    """Get information about a specific commit.

    Args:
        repo_slug: Repository slug
        commit_hash: Full or short commit hash
    """
    result = _get_commit(repo_slug, commit_hash)
    if "error" in result:
        return f"Error: {result['error']}"

    lines = [
        f"Commit: {result['hash']}",
        f"  Message: {result['message']}",
        f"  Author: {result['author']}",
        f"  Date: {result['date']}",
        f"  URL: {result['url']}",
    ]
    return "\n".join(lines)


@tool
def list_branches(repo_slug: str, limit: int = 25) -> str:
    """List branches in a repository.

    Args:
        repo_slug: Repository slug
        limit: Maximum number of branches to return
    """
    result = _list_branches(repo_slug, limit)
    if "error" in result:
        return f"Error: {result['error']}"

    branches = result.get("branches", [])
    if not branches:
        return f"No branches found for {repo_slug}"

    lines = [f"Branches in {repo_slug} ({len(branches)}):"]
    for branch in branches:
        lines.append(f"  {branch['name']} - {branch['target_hash']} ({branch['target_date']})")

    return "\n".join(lines)


# ============================================================================
# EXPORT
# ============================================================================

BITBUCKET_TOOLS = [
    list_pull_requests,
    get_pipeline_status,
    get_repository_info,
    list_repositories,
    get_commit_info,
    list_branches,
]

SYSTEM_PROMPT = """You are a Bitbucket Assistant for the MrRobot development team.

You have access to Bitbucket API tools for repository and CI/CD operations.

TOOLS:
1. list_pull_requests - List PRs (state='OPEN', 'MERGED', 'DECLINED', 'ALL')
2. get_pipeline_status - Check CI/CD pipeline status for a repo
3. get_repository_info - Get details about a specific repo
4. list_repositories - List all repos in the workspace
5. get_commit_info - Get details about a specific commit
6. list_branches - List branches in a repo

For CODE SEARCH, use the MrRobot MCP tools:
- search_mrrobot_repos - Semantic code search
- search_in_repo - Search within a specific repo
- get_file_content - Get full file contents

Example interactions:
- "Show open PRs" -> list_pull_requests(state='OPEN')
- "Check emvio-payment-service builds" -> get_pipeline_status('emvio-payment-service')
- "What repos do we have?" -> list_repositories()
"""


def create_bitbucket_agent():
    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-west-2")
    return Agent(model=model, tools=BITBUCKET_TOOLS, system_prompt=SYSTEM_PROMPT)


bitbucket_agent = None  # Lazy initialization
