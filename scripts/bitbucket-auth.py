#!/usr/bin/env python3
"""Bitbucket API Authentication Helper.

Usage:
    python scripts/bitbucket-auth.py test
    python scripts/bitbucket-auth.py my-prs
    python scripts/bitbucket-auth.py pr <repo> <pr_id>
    python scripts/bitbucket-auth.py prs <repo>
    python scripts/bitbucket-auth.py comments <repo> <pr_id>
    python scripts/bitbucket-auth.py diff <repo> <pr_id>
"""

import os
import re
import sys

import requests

# Config
BB_EMAIL = "gstarkman@nex.io"
BB_API = "https://api.bitbucket.org/2.0"
BB_WORKSPACE = "mrrobot-labs"


def get_token():
    """Get token from env var or extract from ~/.zshrc."""
    token = os.environ.get("BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED")
    if token:
        return token

    zshrc_path = os.path.expanduser("~/.zshrc")
    if os.path.exists(zshrc_path):
        with open(zshrc_path) as f:
            for line in f:
                if "BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED=" in line:
                    match = re.search(r'"([^"]+)"', line)
                    if match:
                        return match.group(1)
    return None


BB_TOKEN = get_token()


def bb_get(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GET request to Bitbucket API."""
    if not BB_TOKEN:
        return {"error": "No token found"}

    url = f"{BB_API}{endpoint}"
    try:
        r = requests.get(url, auth=(BB_EMAIL, BB_TOKEN), params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "message": r.text[:200]}
    except Exception as e:
        return {"error": str(e)}


def cmd_test():
    """Test authentication."""
    print(f"Email: {BB_EMAIL}")
    print(f"Token: {BB_TOKEN[:20]}..." if BB_TOKEN else "Token: NOT SET")
    print()

    result = bb_get("/user")
    if "error" in result:
        print(f"FAILED: {result['error']}")
        return 1

    print(f"SUCCESS: Authenticated as {result.get('display_name', 'unknown')}")
    return 0


def cmd_my_prs():
    """Find all open PRs by current user across all repos."""
    print("Finding your open PRs...")

    # Get all repos in workspace
    repos = []
    page_url = f"/repositories/{BB_WORKSPACE}?pagelen=100"
    while page_url:
        result = bb_get(page_url)
        if "error" in result:
            print(f"Error: {result['error']}")
            return 1
        repos.extend([r["slug"] for r in result.get("values", [])])
        page_url = result.get("next", "").replace(BB_API, "") if result.get("next") else None

    print(f"Searching {len(repos)} repos...")

    # Check each repo for open PRs by Grant
    my_prs = []
    for repo in repos:
        result = bb_get(f"/repositories/{BB_WORKSPACE}/{repo}/pullrequests", {"state": "OPEN"})
        if "error" not in result:
            for pr in result.get("values", []):
                if "Grant" in pr.get("author", {}).get("display_name", ""):
                    my_prs.append(
                        {
                            "repo": repo,
                            "id": pr["id"],
                            "title": pr["title"],
                            "source": pr["source"]["branch"]["name"],
                            "dest": pr["destination"]["branch"]["name"],
                            "created": pr["created_on"][:10],
                            "updated": pr["updated_on"][:10],
                        }
                    )

    print(f"\nYour open PRs: {len(my_prs)}")
    for pr in my_prs:
        print(f"  #{pr['id']} {pr['repo']}: {pr['title'][:50]}")

    return 0


def cmd_pr(repo: str, pr_id: str):
    """Get PR details."""
    result = bb_get(f"/repositories/{BB_WORKSPACE}/{repo}/pullrequests/{pr_id}")
    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"Title: {result['title']}")
    print(f"State: {result['state']}")
    print(f"Author: {result['author']['display_name']}")
    print(f"Source: {result['source']['branch']['name']} -> {result['destination']['branch']['name']}")
    print(f"Created: {result['created_on'][:10]}")
    print(f"Updated: {result['updated_on'][:10]}")
    print(f"Link: https://bitbucket.org/{BB_WORKSPACE}/{repo}/pull-requests/{pr_id}")
    desc = result.get("description") or "None"
    print(f"Description: {desc[:300]}")
    return 0


def cmd_prs(repo: str):
    """List open PRs in a repo."""
    result = bb_get(f"/repositories/{BB_WORKSPACE}/{repo}/pullrequests", {"state": "OPEN"})
    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    prs = result.get("values", [])
    print(f"Open PRs in {repo}: {len(prs)}")
    for pr in prs:
        print(f"  #{pr['id']}: {pr['title'][:60]} ({pr['author']['display_name']})")
    return 0


def cmd_comments(repo: str, pr_id: str):
    """Get PR comments."""
    result = bb_get(f"/repositories/{BB_WORKSPACE}/{repo}/pullrequests/{pr_id}/comments")
    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    comments = result.get("values", [])
    print(f"Comments: {len(comments)}")
    for c in comments:
        user = c.get("user", {}).get("display_name", "Unknown")
        content = c.get("content", {}).get("raw", "")[:300]
        created = c.get("created_on", "")[:10]
        inline = c.get("inline", {})
        if inline:
            path = inline.get("path", "")
            line = inline.get("to") or inline.get("from", "")
            print(f"\n[{created}] {user} on {path}:{line}")
        else:
            print(f"\n[{created}] {user}:")
        print(f"  {content}")
    return 0


def cmd_diff(repo: str, pr_id: str):
    """Get PR diff."""
    # First get PR to find branch names
    pr = bb_get(f"/repositories/{BB_WORKSPACE}/{repo}/pullrequests/{pr_id}")
    if "error" in pr:
        print(f"Error: {pr['error']}")
        return 1

    source = pr["source"]["branch"]["name"]
    dest = pr["destination"]["branch"]["name"]

    # Get diff
    url = f"{BB_API}/repositories/{BB_WORKSPACE}/{repo}/diff/{source}..{dest}"
    try:
        r = requests.get(url, auth=(BB_EMAIL, BB_TOKEN), timeout=30)
        if r.status_code == 200:
            print(r.text[:10000])
        else:
            print(f"Error: HTTP {r.status_code}")
            return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1]

    if cmd == "test":
        return cmd_test()
    elif cmd == "my-prs":
        return cmd_my_prs()
    elif cmd == "pr" and len(sys.argv) >= 4:
        return cmd_pr(sys.argv[2], sys.argv[3])
    elif cmd == "prs" and len(sys.argv) >= 3:
        return cmd_prs(sys.argv[2])
    elif cmd == "comments" and len(sys.argv) >= 4:
        return cmd_comments(sys.argv[2], sys.argv[3])
    elif cmd == "diff" and len(sys.argv) >= 4:
        return cmd_diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
