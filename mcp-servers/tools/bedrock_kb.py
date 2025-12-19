"""Bedrock Knowledge Base tools for code search."""

import json
import os

import boto3
import requests

from ..utils.secrets import get_secret

# Configuration
KB_ID = os.environ.get("CODE_KB_ID", "SAJJWYFTNG")
REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")
BITBUCKET_EMAIL = os.environ.get("BITBUCKET_EMAIL", "gstarkman@nex.io")
BITBUCKET_WORKSPACE = "mrrobot-labs"

# Known repos list (sample)
KNOWN_REPOS = [
    "cast-core", "cast-quickbooks", "cast-housecallpro", "cast-jobber",
    "cast-service-titan", "cast-xero", "cast-databases", "cast-dashboard",
    "mrrobot-auth-rest", "mrrobot-rest-utils-npm", "mrrobot-common-js-utils",
    "mrrobot-sdk", "mrrobot-connector-hub", "mrrobot-risk-rest", "mrrobot-ai-core",
    "emvio-gateway", "emvio-dashboard-app", "emvio-payment-service",
    "emvio-auth-service", "emvio-transactions-service", "emvio-webhook-service",
    "aws-terraform", "bitbucket-terraform", "devops-scripts",
]


def _get_boto_session():
    """Get boto3 session with optional profile."""
    if AWS_PROFILE:
        return boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
    return boto3.Session(region_name=REGION)


def search_knowledge_base(query: str, num_results: int = 5) -> dict:
    """Search the Bedrock Knowledge Base."""
    from botocore.config import Config

    config = Config(connect_timeout=10, read_timeout=25, retries={"max_attempts": 1})
    session = _get_boto_session()
    client = session.client("bedrock-agent-runtime", config=config)

    try:
        response = client.retrieve(
            knowledgeBaseId=KB_ID,
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

            results.append({
                "repo": repo_name,
                "file": file_path,
                "full_path": path,
                "score": round(item.get("score", 0), 3),
                "content": item.get("content", {}).get("text", "")[:1000],
                "bitbucket_url": f"https://bitbucket.org/mrrobot-labs/{repo_name}/src/master/{file_path}",
            })

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


# Tool handlers
def handle_search_mrrobot_repos(query: str, num_results: int = 5) -> dict:
    """Search all MrRobot repos."""
    return search_knowledge_base(query, min(num_results, 10))


def handle_search_in_repo(query: str, repo_name: str, num_results: int = 5) -> dict:
    """Search within a specific repo."""
    combined_query = f"{query} in {repo_name}"
    result = search_knowledge_base(combined_query, min(num_results * 3, 15))
    if "results" in result:
        filtered = [r for r in result["results"] if repo_name.lower() in r.get("repo", "").lower()]
        result["results"] = filtered[:num_results]
    result["repo_filter"] = repo_name
    return result


def handle_find_similar_code(code_snippet: str, num_results: int = 5) -> dict:
    """Find similar code patterns."""
    result = search_knowledge_base(code_snippet, min(num_results, 10))
    result["search_type"] = "similar_code"
    return result


def handle_get_kb_info() -> dict:
    """Get knowledge base info."""
    return {
        "knowledge_base_id": KB_ID,
        "region": REGION,
        "stats": {
            "repositories": 254,
            "documents_indexed": 17169,
            "embedding_model": "amazon.titan-embed-text-v2:0",
            "vector_store": "OpenSearch Serverless",
        },
        "tips": [
            "Use natural language queries - semantic search understands intent",
            "Be specific: 'JWT validation in gateway' beats 'authentication'",
        ],
    }


def handle_get_file_content(repo: str, file_path: str, branch: str = "master") -> dict:
    """Get file content from Bitbucket."""
    return get_file_from_bitbucket(repo, file_path, branch)


def handle_list_repos(filter: str = "") -> dict:
    """List available repos."""
    repos = KNOWN_REPOS
    if filter:
        repos = [r for r in repos if filter.lower() in r.lower()]
    return {
        "total_indexed": 254,
        "matching_repos": repos,
        "count": len(repos),
        "filter": filter or "none",
    }


def handle_search_by_file_type(query: str, file_type: str, num_results: int = 5) -> dict:
    """Search by file type."""
    enhanced_query = f"file:{file_type} {query}"
    result = search_knowledge_base(enhanced_query, num_results)
    if "results" in result:
        result["results"] = [r for r in result["results"] if file_type.lower() in r.get("file", "").lower()]
    result["file_type_filter"] = file_type
    return result


def register_bedrock_kb_tools(protocol):
    """Register all Bedrock KB tools with the MCP protocol handler."""

    protocol.register_tool(
        name="search_mrrobot_repos",
        description="Search ALL 254 MrRobot Bitbucket repositories using AI semantic search. Use for CSP, CORS, auth, Lambda, S3, APIs, or any MrRobot code.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "num_results": {"type": "integer", "description": "Number of results (default: 5, max: 10)", "default": 5},
            },
            "required": ["query"],
        },
        handler=handle_search_mrrobot_repos,
    )

    protocol.register_tool(
        name="search_in_repo",
        description="Search within a SPECIFIC MrRobot repository.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "repo_name": {"type": "string", "description": "Repository name (e.g., 'cast-core')"},
                "num_results": {"type": "integer", "default": 5},
            },
            "required": ["query", "repo_name"],
        },
        handler=handle_search_in_repo,
    )

    protocol.register_tool(
        name="find_similar_code",
        description="Find code similar to a given snippet across all repositories.",
        input_schema={
            "type": "object",
            "properties": {
                "code_snippet": {"type": "string", "description": "Code snippet to find similar patterns for"},
                "num_results": {"type": "integer", "default": 5},
            },
            "required": ["code_snippet"],
        },
        handler=handle_find_similar_code,
    )

    protocol.register_tool(
        name="get_kb_info",
        description="Get information about the MrRobot code knowledge base.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=handle_get_kb_info,
    )

    protocol.register_tool(
        name="get_file_content",
        description="Fetch full file content from Bitbucket.",
        input_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository name"},
                "file_path": {"type": "string", "description": "Path to file"},
                "branch": {"type": "string", "default": "master"},
            },
            "required": ["repo", "file_path"],
        },
        handler=handle_get_file_content,
    )

    protocol.register_tool(
        name="list_repos",
        description="List all MrRobot repositories in the knowledge base.",
        input_schema={
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Optional filter pattern"},
            },
            "required": [],
        },
        handler=handle_list_repos,
    )

    protocol.register_tool(
        name="search_by_file_type",
        description="Search for code patterns in specific file types (e.g., 'serverless.yml', '.tf').",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "file_type": {"type": "string", "description": "File extension or type"},
                "num_results": {"type": "integer", "default": 5},
            },
            "required": ["query", "file_type"],
        },
        handler=handle_search_by_file_type,
    )

