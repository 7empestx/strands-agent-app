"""Bitbucket API tools for MCP server.

Provides tools for repository management, PRs, and CI/CD pipelines.
"""

import os
import sys

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.lib.utils.config import BITBUCKET_EMAIL, BITBUCKET_WORKSPACE
from src.lib.utils.secrets import get_secret


def _get_bitbucket_token() -> str:
    """Get Bitbucket token from Secrets Manager."""
    return get_secret("BITBUCKET_TOKEN")


def _fetch_pipeline_log(endpoint: str) -> str:
    """Fetch raw pipeline log text (not JSON)."""
    import time

    token = _get_bitbucket_token()
    if not token:
        return ""

    try:
        url = f"https://api.bitbucket.org/2.0/{endpoint}"
        print(f"[Bitbucket] Fetching log: {endpoint}")
        start = time.time()
        response = requests.get(url, auth=(BITBUCKET_EMAIL, token), timeout=10)
        elapsed = time.time() - start
        print(f"[Bitbucket] Log response: {response.status_code} in {elapsed:.1f}s")

        if response.status_code == 200:
            return response.text
        return ""
    except Exception as e:
        print(f"[Bitbucket] Log fetch error: {e}")
        return ""


def _make_bitbucket_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated request to Bitbucket API."""
    import time

    token = _get_bitbucket_token()
    if not token:
        return {"error": "BITBUCKET_TOKEN not configured"}

    try:
        url = f"https://api.bitbucket.org/2.0/{endpoint}"
        print(f"[Bitbucket] Requesting: {endpoint}")
        start = time.time()
        response = requests.get(url, auth=(BITBUCKET_EMAIL, token), params=params, timeout=10)

        elapsed = time.time() - start
        print(f"[Bitbucket] Response: {response.status_code} in {elapsed:.1f}s")

        if response.status_code == 404:
            return {"error": f"Not found: {endpoint}"}
        elif response.status_code == 403:
            return {"error": "Bitbucket API returned 403 Forbidden. The mrrobot-labs workspace requires VPN access, and this server isn't on the VPN. PR details can't be fetched automatically - please use the Bitbucket link directly."}
        elif response.status_code == 401:
            return {"error": "Bitbucket API error: 401 Unauthorized. Check BITBUCKET_TOKEN in Secrets Manager."}
        elif response.status_code != 200:
            return {"error": f"Bitbucket API error: {response.status_code}"}

        return response.json()
    except requests.exceptions.Timeout:
        print(f"[Bitbucket] Timeout after 15s for {endpoint}")
        return {"error": f"Bitbucket API timeout for {endpoint}. The API may be slow or unavailable."}
    except Exception as e:
        print(f"[Bitbucket] Error: {e}")
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
        prs.append(
            {
                "id": pr.get("id"),
                "title": pr.get("title", "No title"),
                "author": pr.get("author", {}).get("display_name", "Unknown"),
                "created": pr.get("created_on", "")[:10],
                "state": pr.get("state", ""),
                "repo": pr.get("destination", {}).get("repository", {}).get("name", ""),
                "source_branch": pr.get("source", {}).get("branch", {}).get("name", ""),
                "dest_branch": pr.get("destination", {}).get("branch", {}).get("name", ""),
                "url": pr.get("links", {}).get("html", {}).get("href", ""),
            }
        )

    return {"pull_requests": prs, "state": state, "count": len(prs)}


def get_open_prs(repo_slug: str, limit: int = 5) -> dict:
    """Get open pull requests for a repository (convenience wrapper).
    
    Args:
        repo_slug: Repository slug (e.g., 'mrrobot-auth-rest')
        limit: Max PRs to return (default: 5)
    
    Returns:
        dict with 'pull_requests' list
    """
    return list_pull_requests(repo_slug=repo_slug, state="OPEN", limit=limit)


def get_pr_details(repo_slug: str, pr_id: int) -> dict:
    """Get detailed information about a pull request including diff.

    Args:
        repo_slug: Repository slug (e.g., 'cforce-service')
        pr_id: Pull request ID number

    Returns:
        dict with PR details, diff summary, and files changed
    """
    # Get PR info
    pr_endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/pullrequests/{pr_id}"
    pr_data = _make_bitbucket_request(pr_endpoint)

    if "error" in pr_data:
        return pr_data

    # Get diff stat (files changed)
    diffstat_endpoint = f"{pr_endpoint}/diffstat"
    diffstat = _make_bitbucket_request(diffstat_endpoint)

    files_changed = []
    if "values" in diffstat:
        for file in diffstat.get("values", [])[:20]:  # Limit to 20 files
            old_info = file.get("old") or {}
            new_info = file.get("new") or {}
            old_path = old_info.get("path", "")
            new_path = new_info.get("path", "")
            status = file.get("status", "")
            lines_added = file.get("lines_added", 0)
            lines_removed = file.get("lines_removed", 0)

            files_changed.append({
                "path": new_path or old_path,
                "status": status,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
            })

    # Get activity/comments
    activity_endpoint = f"{pr_endpoint}/activity"
    activity_data = _make_bitbucket_request(activity_endpoint, {"pagelen": 10})

    comments = []
    approvals = []
    if "values" in activity_data:
        for item in activity_data.get("values", []):
            if "comment" in item:
                comment = item["comment"]
                comments.append({
                    "author": comment.get("user", {}).get("display_name", ""),
                    "content": comment.get("content", {}).get("raw", "")[:200],
                    "created": comment.get("created_on", "")[:16],
                })
            if "approval" in item:
                approval = item["approval"]
                approvals.append({
                    "user": approval.get("user", {}).get("display_name", ""),
                    "date": approval.get("date", "")[:16],
                })

    return {
        "pr_id": pr_id,
        "repo": repo_slug,
        "title": pr_data.get("title", ""),
        "description": pr_data.get("description", "")[:500] if pr_data.get("description") else "",
        "author": pr_data.get("author", {}).get("display_name", ""),
        "state": pr_data.get("state", ""),
        "source_branch": pr_data.get("source", {}).get("branch", {}).get("name", ""),
        "dest_branch": pr_data.get("destination", {}).get("branch", {}).get("name", ""),
        "created": pr_data.get("created_on", "")[:16].replace("T", " "),
        "updated": pr_data.get("updated_on", "")[:16].replace("T", " "),
        "url": pr_data.get("links", {}).get("html", {}).get("href", ""),
        "files_changed": files_changed,
        "total_files": len(files_changed),
        "total_additions": sum(f.get("lines_added", 0) for f in files_changed),
        "total_deletions": sum(f.get("lines_removed", 0) for f in files_changed),
        "approvals": approvals,
        "comments": comments,
    }


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

        pipelines.append(
            {
                "build_number": pipe.get("build_number"),
                "state": state,
                "result": result or state,
                "branch": pipe.get("target", {}).get("ref_name", "N/A"),
                "created": pipe.get("created_on", "")[:16].replace("T", " "),
                "duration_seconds": pipe.get("duration_in_seconds"),
                "url": pipe.get("links", {}).get("html", {}).get("href", ""),
            }
        )

    return {"pipelines": pipelines, "repo": repo_slug, "count": len(pipelines)}


def get_pipeline_details(repo_slug: str, pipeline_id: int) -> dict:
    """Get detailed information about a specific pipeline/build including failure reason.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-underwriting-service')
        pipeline_id: Pipeline/build number (e.g., 2346)

    Returns:
        dict with pipeline details, steps, and failure info
    """
    # Get pipeline info
    endpoint = f"repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/pipelines/{pipeline_id}"
    data = _make_bitbucket_request(endpoint)

    if "error" in data:
        return data

    state = data.get("state", {}).get("name", "Unknown")
    result = data.get("state", {}).get("result", {}).get("name", "")

    pipeline_info = {
        "build_number": data.get("build_number"),
        "state": state,
        "result": result or state,
        "branch": data.get("target", {}).get("ref_name", "N/A"),
        "commit": data.get("target", {}).get("commit", {}).get("hash", "")[:8],
        "commit_message": data.get("target", {}).get("commit", {}).get("message", "")[:100],
        "author": data.get("creator", {}).get("display_name", "Unknown"),
        "created": data.get("created_on", "")[:16].replace("T", " "),
        "completed": data.get("completed_on", "")[:16].replace("T", " ") if data.get("completed_on") else None,
        "duration_seconds": data.get("duration_in_seconds"),
        "url": data.get("links", {}).get("html", {}).get("href", ""),
    }

    # Get steps to find failure details
    steps_endpoint = f"{endpoint}/steps/"
    steps_data = _make_bitbucket_request(steps_endpoint)

    steps = []
    failed_step = None
    if "values" in steps_data:
        for step in steps_data.get("values", []):
            step_state = step.get("state", {}).get("name", "Unknown")
            step_result = step.get("state", {}).get("result", {}).get("name", "")

            step_info = {
                "name": step.get("name", "Unnamed step"),
                "state": step_state,
                "result": step_result or step_state,
                "duration_seconds": step.get("duration_in_seconds"),
            }
            steps.append(step_info)

            # Track the failed step
            if step_result == "FAILED" and not failed_step:
                failed_step = step_info
                # Try to get the log for this step
                step_uuid = step.get("uuid", "")
                if step_uuid:
                    log_endpoint = f"{endpoint}/steps/{step_uuid}/log"
                    log_text = _fetch_pipeline_log(log_endpoint)
                    if log_text:
                        # Extract the most relevant error lines
                        log_lines = log_text.strip().split("\n")
                        error_lines = []
                        for i, line in enumerate(log_lines):
                            line_lower = line.lower()
                            if ("failed" in line_lower or "error" in line_lower or
                                "exit code" in line_lower or "exception" in line_lower or
                                "traceback" in line_lower):
                                # Get context: 2 lines before, the error line, 2 lines after
                                start = max(0, i - 2)
                                end = min(len(log_lines), i + 3)
                                error_lines.extend(log_lines[start:end])
                                error_lines.append("---")
                        if error_lines:
                            failed_step["error_context"] = "\n".join(error_lines[-40:])
                        # Also keep tail for full context
                        failed_step["log_tail"] = "\n".join(log_lines[-30:])

    pipeline_info["steps"] = steps
    pipeline_info["failed_step"] = failed_step

    return pipeline_info


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
        repos.append(
            {
                "name": repo.get("name"),
                "slug": repo.get("slug"),
                "language": repo.get("language", ""),
                "updated": repo.get("updated_on", "")[:10],
                "url": repo.get("links", {}).get("html", {}).get("href", ""),
            }
        )

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
        branches.append(
            {
                "name": branch.get("name"),
                "target_hash": branch.get("target", {}).get("hash", "")[:12],
                "target_date": branch.get("target", {}).get("date", "")[:10],
            }
        )

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
