"""Code Search tools using Amazon Bedrock Knowledge Base.

Provides semantic search across 254 MrRobot repositories (17,169 documents).
"""

import os
import sys

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.lib.utils.aws import get_bedrock_agent_runtime
from src.lib.utils.config import BITBUCKET_EMAIL, BITBUCKET_WORKSPACE, KNOWLEDGE_BASE_ID
from src.lib.utils.secrets import get_secret

# Alias for backward compatibility
KB_ID = KNOWLEDGE_BASE_ID

# Note: Repo list is dynamic - stored in S3 and indexed in OpenSearch.
# Use the MCP mrrobot-code-kb list_repos tool to get the full list of 254 repos.


def search_knowledge_base(query: str, num_results: int = 10) -> dict:
    """Search the Bedrock Knowledge Base for code across MrRobot repositories.

    Args:
        query: Natural language search query (e.g., 'payment processing logic')
        num_results: Number of results to return (default: 10, max: 25)

    Returns:
        dict with results array containing repo, file, score, content snippet, and URLs
    """
    client = get_bedrock_agent_runtime()

    # Cap results at 25 to avoid overwhelming responses
    num_results = min(num_results, 25)

    try:
        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": num_results}},
        )

        retrieval_results = response.get("retrievalResults", [])
        results = []

        for item in retrieval_results:
            location = item.get("location", {}).get("s3Location", {}).get("uri", "")
            if "/repos/" in location:
                path = location.split("/repos/")[1]
            else:
                path = location

            repo_name = path.split("/")[0] if "/" in path else path
            file_path = "/".join(path.split("/")[1:]) if "/" in path else path

            # Extract file extension
            file_ext = ""
            if "." in file_path:
                file_ext = file_path.rsplit(".", 1)[-1]

            # Get content with smarter truncation (try to end at newline)
            raw_content = item.get("content", {}).get("text", "")
            content = _smart_truncate(raw_content, max_length=2000)

            score = item.get("score", 0)

            results.append(
                {
                    "repo": repo_name,
                    "file": file_path,
                    "file_type": file_ext,
                    "full_path": path,
                    "score": round(score, 3),
                    "relevance": _score_to_relevance(score),
                    "content": content,
                    "bitbucket_url": f"https://bitbucket.org/mrrobot-labs/{repo_name}/src/master/{file_path}",
                }
            )

        return {
            "results": results,
            "query": query,
            "total_found": len(results),
            "requested": num_results,
        }
    except Exception as e:
        return {"error": str(e)}


def _smart_truncate(text: str, max_length: int = 2000) -> str:
    """Truncate text at a natural boundary (newline) if possible."""
    if len(text) <= max_length:
        return text

    # Try to find a newline near the max_length to cut at
    truncated = text[:max_length]
    last_newline = truncated.rfind("\n")

    # If we find a newline in the last 20% of the text, cut there
    if last_newline > max_length * 0.8:
        return truncated[:last_newline] + "\n... [truncated]"

    return truncated + "\n... [truncated]"


def _score_to_relevance(score: float) -> str:
    """Convert numeric score to human-readable relevance."""
    if score >= 0.8:
        return "high"
    elif score >= 0.6:
        return "medium"
    elif score >= 0.4:
        return "low"
    else:
        return "weak"


def get_file_from_bitbucket(repo: str, file_path: str, branch: str = "master") -> dict:
    """Fetch full file content from Bitbucket API."""
    token = get_secret("BITBUCKET_TOKEN") or get_secret("CVE_BB_TOKEN")
    if not token:
        return {"error": "BITBUCKET_TOKEN not configured"}

    try:
        url = f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}/{repo}/src/{branch}/{file_path}"
        response = requests.get(url, auth=(BITBUCKET_EMAIL, token), timeout=30)

        if response.status_code == 404:
            return {"error": f"File not found: {repo}/{file_path}"}
        elif response.status_code != 200:
            return {"error": f"Bitbucket API error: {response.status_code}"}

        content = response.text
        if len(content) > 50000:
            content = content[:50000] + f"\n\n... [truncated - file is {len(response.text)} bytes]"

        return {
            "repo": repo,
            "file": file_path,
            "branch": branch,
            "content": content,
            "size_bytes": len(response.text),
            "bitbucket_url": f"https://bitbucket.org/{BITBUCKET_WORKSPACE}/{repo}/src/{branch}/{file_path}",
        }
    except Exception as e:
        return {"error": str(e)}
