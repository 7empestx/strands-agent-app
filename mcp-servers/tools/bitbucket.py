"""Bitbucket API tools for MCP server.

Provides tools for repository management, PRs, and CI/CD pipelines.
"""

import sys
import os

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.config import BITBUCKET_EMAIL, BITBUCKET_WORKSPACE
from utils.secrets import get_secret


def _get_bitbucket_token() -> str:
    """Get Bitbucket token from env var or Secrets Manager."""
    return get_secret("CVE_BB_TOKEN") or get_secret("BITBUCKET_TOKEN")


def _make_bitbucket_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated request to Bitbucket API."""
    token = _get_bitbucket_token()
    if not token:
        return {"error": "BITBUCKET_TOKEN not configured"}

    try:
        url = f"https://api.bitbucket.org/2.0/{endpoint}"
        response = requests.get(url, auth=(BITBUCKET_EMAIL, token), params=params, timeout=30)

        if response.status_code == 404:
            return {"error": f"Not found: {endpoint}"}
        elif response.status_code != 200:
            return {"error": f"Bitbucket API error: {response.status_code}"}

        return response.json()
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# BITBUCKET API FUNCTIONS
# ============================================================================


def list_pull_requests(repo_slug: str = "", state: str = "OPEN", limit: int = 20) -> dict:
    """List pull requests from Bitbucket.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-dashboard-app'). Empty = all repos
        state: PR state - OPEN, MERGED, DECLINED, or ALL
        limit: Maximum number of PRs to return

    Returns:
        dict with 'pull_requests' list or 'error'
    """
    if repo_slug:
        endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/pullrequests"
    else:
        endpoint = f"pullrequests/{BITBUCKET_WORKSPACE}"

    data = _make_bitbucket_request(endpoint, {"state": state, "pagelen": limit})

    if "error" in data:
        return data

    prs = []
    for pr in data.get("values", [])[:limit]:
        prs.append({
            "id": pr.get("id"),
            "title": pr.get("title", "No title"),
            "author": pr.get("author", {}).get("display_name", "Unknown"),
            "created": pr.get("created_on", "")[:10],
            "state": pr.get("state", ""),
            "repo": pr.get("destination", {}).get("repository", {}).get("name", ""),
            "source_branch": pr.get("source", {}).get("branch", {}).get("name", ""),
            "dest_branch": pr.get("destination", {}).get("branch", {}).get("name", ""),
            "url": pr.get("links", {}).get("html", {}).get("href", ""),
        })

    return {"pull_requests": prs, "state": state, "count": len(prs)}


def get_pipeline_status(repo_slug: str, limit: int = 5) -> dict:
    """Get recent pipeline/build status for a repository.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-payment-service')
        limit: Number of recent pipelines to return

    Returns:
        dict with 'pipelines' list or 'error'
    """
    endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/pipelines/"
    data = _make_bitbucket_request(endpoint, {"pagelen": limit, "sort": "-created_on"})

    if "error" in data:
        return data

    pipelines = []
    for pipe in data.get("values", []):
        state = pipe.get("state", {}).get("name", "Unknown")
        result = pipe.get("state", {}).get("result", {}).get("name", "")

        pipelines.append({
            "build_number": pipe.get("build_number"),
            "state": state,
            "result": result or state,
            "branch": pipe.get("target", {}).get("ref_name", "N/A"),
            "created": pipe.get("created_on", "")[:16].replace("T", " "),
            "duration_seconds": pipe.get("duration_in_seconds"),
            "url": pipe.get("links", {}).get("html", {}).get("href", ""),
        })

    return {"pipelines": pipelines, "repo": repo_slug, "count": len(pipelines)}


def get_repository_info(repo_slug: str) -> dict:
    """Get detailed information about a repository.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-dashboard-app')

    Returns:
        dict with repository details or 'error'
    """
    endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}"
    data = _make_bitbucket_request(endpoint)

    if "error" in data:
        return data

    return {
        "name": data.get("name"),
        "slug": data.get("slug"),
        "full_name": data.get("full_name"),
        "description": data.get("description", "No description"),
        "language": data.get("language", "N/A"),
        "created": data.get("created_on", "")[:10],
        "updated": data.get("updated_on", "")[:10],
        "main_branch": data.get("mainbranch", {}).get("name", "N/A"),
        "is_private": data.get("is_private", True),
        "url": data.get("links", {}).get("html", {}).get("href", ""),
    }


def list_repositories(limit: int = 50) -> dict:
    """List all repositories in the workspace.

    Args:
        limit: Maximum number of repos to return

    Returns:
        dict with 'repositories' list or 'error'
    """
    endpoint = f"repositories/{BITBUCKET_WORKSPACE}"
    data = _make_bitbucket_request(endpoint, {"pagelen": limit, "sort": "-updated_on"})

    if "error" in data:
        return data

    repos = []
    for repo in data.get("values", []):
        repos.append({
            "name": repo.get("name"),
            "slug": repo.get("slug"),
            "language": repo.get("language", ""),
            "updated": repo.get("updated_on", "")[:10],
            "url": repo.get("links", {}).get("html", {}).get("href", ""),
        })

    return {"repositories": repos, "workspace": BITBUCKET_WORKSPACE, "count": len(repos)}


def get_commit_info(repo_slug: str, commit_hash: str) -> dict:
    """Get information about a specific commit.

    Args:
        repo_slug: Repository slug
        commit_hash: Full or short commit hash

    Returns:
        dict with commit details or 'error'
    """
    endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/commit/{commit_hash}"
    data = _make_bitbucket_request(endpoint)

    if "error" in data:
        return data

    return {
        "hash": data.get("hash", "")[:12],
        "full_hash": data.get("hash"),
        "message": data.get("message", "").strip(),
        "author": data.get("author", {}).get("user", {}).get("display_name", data.get("author", {}).get("raw", "")),
        "date": data.get("date", "")[:16].replace("T", " "),
        "url": data.get("links", {}).get("html", {}).get("href", ""),
    }


def list_branches(repo_slug: str, limit: int = 25) -> dict:
    """List branches in a repository.

    Args:
        repo_slug: Repository slug
        limit: Maximum number of branches to return

    Returns:
        dict with 'branches' list or 'error'
    """
    endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/refs/branches"
    data = _make_bitbucket_request(endpoint, {"pagelen": limit})

    if "error" in data:
        return data

    branches = []
    for branch in data.get("values", []):
        branches.append({
            "name": branch.get("name"),
            "target_hash": branch.get("target", {}).get("hash", "")[:12],
            "target_date": branch.get("target", {}).get("date", "")[:10],
        })

    return {"branches": branches, "repo": repo_slug, "count": len(branches)}


# ============================================================================
# MCP TOOL REGISTRATION
# ============================================================================


def register_tools(mcp):
    """Register Bitbucket tools with the MCP server."""

    @mcp.tool()
    def bitbucket_list_prs(
        repo_slug: str = "",
        state: str = "OPEN",
        limit: int = 20,
    ) -> dict:
        """List pull requests from Bitbucket.

        Args:
            repo_slug: Repository slug (empty for all repos)
            state: OPEN, MERGED, DECLINED, or ALL
            limit: Maximum PRs to return

        Returns:
            List of pull requests with title, author, dates
        """
        return list_pull_requests(repo_slug, state, limit)

    @mcp.tool()
    def bitbucket_pipeline_status(repo_slug: str, limit: int = 5) -> dict:
        """Get recent CI/CD pipeline status for a repository.

        Args:
            repo_slug: Repository slug (e.g., 'emvio-payment-service')
            limit: Number of recent pipelines

        Returns:
            List of recent pipelines with status and branch
        """
        return get_pipeline_status(repo_slug, limit)

    @mcp.tool()
    def bitbucket_repo_info(repo_slug: str) -> dict:
        """Get detailed information about a Bitbucket repository.

        Args:
            repo_slug: Repository slug (e.g., 'emvio-dashboard-app')

        Returns:
            Repository details including language, description, main branch
        """
        return get_repository_info(repo_slug)

    @mcp.tool()
    def bitbucket_list_repos(limit: int = 50) -> dict:
        """List all repositories in the MrRobot Bitbucket workspace.

        Args:
            limit: Maximum repos to return (default 50)

        Returns:
            List of repositories with names and last update dates
        """
        return list_repositories(limit)

    @mcp.tool()
    def bitbucket_commit_info(repo_slug: str, commit_hash: str) -> dict:
        """Get information about a specific commit.

        Args:
            repo_slug: Repository slug
            commit_hash: Full or short commit hash

        Returns:
            Commit details including message, author, date
        """
        return get_commit_info(repo_slug, commit_hash)

    @mcp.tool()
    def bitbucket_list_branches(repo_slug: str, limit: int = 25) -> dict:
        """List branches in a Bitbucket repository.

        Args:
            repo_slug: Repository slug
            limit: Maximum branches to return

        Returns:
            List of branches with latest commit info
        """
        return list_branches(repo_slug, limit)

