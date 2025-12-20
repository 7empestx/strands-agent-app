"""Code Search tools using Amazon Bedrock Knowledge Base.

Provides semantic search across 254 MrRobot repositories (17,169 documents).
"""

import os
import sys

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.aws import get_bedrock_agent_runtime
from utils.config import BITBUCKET_EMAIL, BITBUCKET_WORKSPACE, KNOWLEDGE_BASE_ID
from utils.secrets import get_secret

# Alias for backward compatibility
KB_ID = KNOWLEDGE_BASE_ID

# Known repos list (sample)
KNOWN_REPOS = [
    "cast-core",
    "cast-quickbooks",
    "cast-housecallpro",
    "cast-jobber",
    "cast-service-titan",
    "cast-xero",
    "cast-databases",
    "cast-dashboard",
    "mrrobot-auth-rest",
    "mrrobot-rest-utils-npm",
    "mrrobot-common-js-utils",
    "mrrobot-sdk",
    "mrrobot-connector-hub",
    "mrrobot-risk-rest",
    "mrrobot-ai-core",
    "emvio-gateway",
    "emvio-dashboard-app",
    "emvio-payment-service",
    "emvio-auth-service",
    "emvio-transactions-service",
    "emvio-webhook-service",
    "aws-terraform",
    "bitbucket-terraform",
    "devops-scripts",
]


def search_knowledge_base(query: str, num_results: int = 5) -> dict:
    """Search the Bedrock Knowledge Base."""
    client = get_bedrock_agent_runtime()

    try:
        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": num_results}},
        )

        results = []
        for item in response.get("retrievalResults", []):
            location = item.get("location", {}).get("s3Location", {}).get("uri", "")
            if "/repos/" in location:
                path = location.split("/repos/")[1]
            else:
                path = location

            repo_name = path.split("/")[0] if "/" in path else path
            file_path = "/".join(path.split("/")[1:]) if "/" in path else path

            results.append(
                {
                    "repo": repo_name,
                    "file": file_path,
                    "full_path": path,
                    "score": round(item.get("score", 0), 3),
                    "content": item.get("content", {}).get("text", "")[:1000],
                    "bitbucket_url": f"https://bitbucket.org/mrrobot-labs/{repo_name}/src/master/{file_path}",
                }
            )

        return {"results": results, "query": query}
    except Exception as e:
        return {"error": str(e)}


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
