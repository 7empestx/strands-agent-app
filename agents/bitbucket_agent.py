"""
Bitbucket Agent - Repository and code management
Uses AWS Bedrock Knowledge Base for semantic code search.

The Knowledge Base indexes all Bitbucket repos synced to S3.
"""

import os

import boto3
from strands import Agent, tool
from strands.models import BedrockModel

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "dev")
KNOWLEDGE_BASE_ID = os.environ.get("CODE_KB_ID", "")  # Set after terraform apply
S3_BUCKET = os.environ.get("CODE_KB_BUCKET", "")  # Set after terraform apply

# Bitbucket config (for non-KB operations)
BITBUCKET_TOKEN = os.environ.get("CVE_BB_TOKEN", "")
BITBUCKET_WORKSPACE = os.environ.get("BITBUCKET_WORKSPACE", "mrrobot-labs")
BITBUCKET_EMAIL = os.environ.get("BITBUCKET_EMAIL", "gstarkman@nex.io")


def _get_bedrock_agent_runtime():
    """Get Bedrock Agent Runtime client."""
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("bedrock-agent-runtime")


def _get_s3_client():
    """Get S3 client."""
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("s3")


# ============================================================================
# KNOWLEDGE BASE TOOLS - Semantic Code Search
# ============================================================================


@tool
def search_code(query: str, num_results: int = 10) -> str:
    """Search code across all repositories using semantic search.

    Uses AWS Bedrock Knowledge Base with vector embeddings to find
    relevant code based on meaning, not just keywords.

    Args:
        query: Natural language query (e.g., "CSP configuration", "S3 upload handler")
        num_results: Number of results to return (default 10)

    Examples:
        - "Content Security Policy configuration"
        - "S3 file upload handling"
        - "authentication middleware"
        - "database connection pool"
    """
    if not KNOWLEDGE_BASE_ID:
        return "Error: CODE_KB_ID environment variable not set. Run terraform apply first."

    try:
        client = _get_bedrock_agent_runtime()

        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": num_results}},
        )

        results = []
        for i, result in enumerate(response.get("retrievalResults", []), 1):
            content = result.get("content", {}).get("text", "")
            location = result.get("location", {})
            s3_uri = location.get("s3Location", {}).get("uri", "")
            score = result.get("score", 0)

            # Extract repo/file from S3 URI: s3://bucket/repos/repo-name/path/to/file
            file_info = "Unknown"
            if s3_uri:
                parts = s3_uri.replace("s3://", "").split("/")
                if len(parts) > 2:
                    repo = parts[2] if len(parts) > 2 else ""
                    file_path = "/".join(parts[3:]) if len(parts) > 3 else ""
                    file_info = f"{repo}/{file_path}"

            # Truncate content for readability
            preview = content[:500] + "..." if len(content) > 500 else content

            results.append(
                f"""
--- Result {i} (score: {score:.2f}) ---
File: {file_info}
Content:
{preview}
"""
            )

        if not results:
            return f"No code found matching: '{query}'"

        return f"Found {len(results)} code matches for '{query}':\n" + "\n".join(results)

    except Exception as e:
        return f"Error searching code: {e}"


@tool
def search_code_in_repo(query: str, repo_name: str, num_results: int = 5) -> str:
    """Search code within a specific repository.

    Args:
        query: Natural language query
        repo_name: Repository name to search in (e.g., 'emvio-dashboard-app')
        num_results: Number of results to return
    """
    if not KNOWLEDGE_BASE_ID:
        return "Error: CODE_KB_ID environment variable not set. Run terraform apply first."

    try:
        client = _get_bedrock_agent_runtime()

        # Use filter to restrict to specific repo
        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": f"{query} in {repo_name}"},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": num_results * 2,  # Get more, filter later
                    "filter": {"equals": {"key": "repo_name", "value": repo_name}},
                }
            },
        )

        results = []
        for i, result in enumerate(response.get("retrievalResults", []), 1):
            content = result.get("content", {}).get("text", "")
            location = result.get("location", {})
            s3_uri = location.get("s3Location", {}).get("uri", "")
            score = result.get("score", 0)

            # Filter by repo name in URI if filter didn't work
            if repo_name.lower() not in s3_uri.lower():
                continue

            # Extract file path
            file_info = "Unknown"
            if s3_uri:
                parts = s3_uri.replace("s3://", "").split("/")
                if len(parts) > 3:
                    file_path = "/".join(parts[3:])
                    file_info = file_path

            preview = content[:500] + "..." if len(content) > 500 else content

            results.append(
                f"""
--- Result {i} (score: {score:.2f}) ---
File: {file_info}
Content:
{preview}
"""
            )

            if len(results) >= num_results:
                break

        if not results:
            return f"No code found in '{repo_name}' matching: '{query}'"

        return f"Found {len(results)} matches in {repo_name}:\n" + "\n".join(results)

    except Exception as e:
        return f"Error searching code: {e}"


@tool
def ask_about_code(question: str) -> str:
    """Ask a natural language question about the codebase.

    Uses RetrieveAndGenerate to find relevant code AND generate an answer.
    Great for questions like "How does X work?" or "Where is Y configured?"

    Args:
        question: Natural language question about the code

    Examples:
        - "How is authentication implemented?"
        - "Where is the Content Security Policy configured?"
        - "What database is used for merchant data?"
        - "How do file uploads work in the dashboard?"
    """
    if not KNOWLEDGE_BASE_ID:
        return "Error: CODE_KB_ID environment variable not set. Run terraform apply first."

    try:
        client = _get_bedrock_agent_runtime()

        response = client.retrieve_and_generate(
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": f"arn:aws:bedrock:{AWS_REGION}::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0",
                    "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 5}},
                },
            },
        )

        output = response.get("output", {}).get("text", "No answer generated")

        # Include citations
        citations = response.get("citations", [])
        sources = []
        for citation in citations:
            for ref in citation.get("retrievedReferences", []):
                location = ref.get("location", {})
                s3_uri = location.get("s3Location", {}).get("uri", "")
                if s3_uri:
                    parts = s3_uri.replace("s3://", "").split("/")
                    if len(parts) > 2:
                        repo = parts[2]
                        file_path = "/".join(parts[3:]) if len(parts) > 3 else ""
                        sources.append(f"  - {repo}/{file_path}")

        result = f"Answer:\n{output}"
        if sources:
            result += f"\n\nSources:\n" + "\n".join(set(sources))

        return result

    except Exception as e:
        return f"Error: {e}"


@tool
def find_file(filename: str, num_results: int = 10) -> str:
    """Find files by name or pattern.

    Args:
        filename: Full or partial filename to search for (e.g., 'serverless.yml', 'csp')
        num_results: Maximum number of results
    """
    if not S3_BUCKET:
        return "Error: CODE_KB_BUCKET environment variable not set."

    try:
        s3 = _get_s3_client()

        # List objects in the bucket under repos/
        paginator = s3.get_paginator("list_objects_v2")

        matches = []
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="repos/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if filename.lower() in key.lower():
                    # Extract repo and path
                    parts = key.split("/")
                    if len(parts) > 2:
                        repo = parts[1]
                        file_path = "/".join(parts[2:])
                        matches.append(f"{repo}/{file_path}")

                if len(matches) >= num_results:
                    break

            if len(matches) >= num_results:
                break

        if not matches:
            return f"No files found matching '{filename}'"

        return f"Found {len(matches)} files matching '{filename}':\n" + "\n".join(f"  - {m}" for m in matches)

    except Exception as e:
        return f"Error searching files: {e}"


@tool
def list_indexed_repositories() -> str:
    """List all repositories indexed in the Knowledge Base."""
    if not S3_BUCKET:
        return "Error: CODE_KB_BUCKET environment variable not set."

    try:
        s3 = _get_s3_client()

        # List top-level "directories" under repos/
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="repos/", Delimiter="/")

        repos = []
        for prefix in response.get("CommonPrefixes", []):
            repo_name = prefix["Prefix"].replace("repos/", "").rstrip("/")
            if repo_name:
                repos.append(repo_name)

        if not repos:
            return "No repositories indexed yet. Run sync-repos-to-s3.py to populate."

        return f"Indexed repositories ({len(repos)}):\n" + "\n".join(f"  - {r}" for r in sorted(repos))

    except Exception as e:
        return f"Error listing repositories: {e}"


@tool
def get_knowledge_base_status() -> str:
    """Check the status of the Code Knowledge Base."""
    status_info = []

    # Check env vars
    status_info.append("Configuration:")
    status_info.append(f"  Knowledge Base ID: {KNOWLEDGE_BASE_ID or 'NOT SET'}")
    status_info.append(f"  S3 Bucket: {S3_BUCKET or 'NOT SET'}")
    status_info.append(f"  AWS Region: {AWS_REGION}")

    if not KNOWLEDGE_BASE_ID:
        status_info.append("\nTo configure, run:")
        status_info.append("  1. cd infrastructure && terraform apply")
        status_info.append("  2. Export CODE_KB_ID and CODE_KB_BUCKET from terraform output")
        status_info.append("  3. Run scripts/sync-repos-to-s3.py to populate the KB")
        return "\n".join(status_info)

    # Try to get KB info
    try:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        client = session.client("bedrock-agent")

        kb_response = client.get_knowledge_base(knowledgeBaseId=KNOWLEDGE_BASE_ID)
        kb = kb_response.get("knowledgeBase", {})

        status_info.append(f"\nKnowledge Base Status:")
        status_info.append(f"  Name: {kb.get('name', 'N/A')}")
        status_info.append(f"  Status: {kb.get('status', 'N/A')}")
        status_info.append(f"  Updated: {kb.get('updatedAt', 'N/A')}")

    except Exception as e:
        status_info.append(f"\nCould not fetch KB details: {e}")

    # Try to count files in S3
    if S3_BUCKET:
        try:
            s3 = _get_s3_client()
            response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="repos/", MaxKeys=1)
            count = response.get("KeyCount", 0)
            status_info.append(f"\nS3 Content: {'Files present' if count > 0 else 'Empty - run sync script'}")
        except Exception as e:
            status_info.append(f"\nCould not check S3: {e}")

    return "\n".join(status_info)


# ============================================================================
# BITBUCKET API TOOLS - Direct API access for PRs, Pipelines
# ============================================================================


@tool
def list_pull_requests(repo_slug: str = "", state: str = "OPEN", limit: int = 20) -> str:
    """List pull requests from Bitbucket.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-dashboard-app'). Empty = all repos
        state: PR state - OPEN, MERGED, DECLINED, or ALL
        limit: Maximum number of PRs to return
    """
    if not BITBUCKET_TOKEN:
        return "Error: CVE_BB_TOKEN environment variable not set."

    import requests

    try:
        # Build URL
        if repo_slug:
            url = f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/pullrequests"
        else:
            url = f"https://api.bitbucket.org/2.0/pullrequests/{BITBUCKET_WORKSPACE}"

        params = {"state": state, "pagelen": limit}
        response = requests.get(url, auth=(BITBUCKET_EMAIL, BITBUCKET_TOKEN), params=params)

        if response.status_code != 200:
            return f"Error fetching PRs: {response.status_code}"

        data = response.json()
        prs = data.get("values", [])

        if not prs:
            return f"No {state} pull requests found"

        results = [f"Pull Requests ({state}):"]
        for pr in prs[:limit]:
            title = pr.get("title", "No title")
            author = pr.get("author", {}).get("display_name", "Unknown")
            created = pr.get("created_on", "")[:10]
            pr_id = pr.get("id", "")
            repo = pr.get("destination", {}).get("repository", {}).get("name", "")

            results.append(f"  [{repo}] #{pr_id}: {title}")
            results.append(f"      Author: {author} | Created: {created}")

        return "\n".join(results)

    except Exception as e:
        return f"Error: {e}"


@tool
def get_pipeline_status(repo_slug: str, limit: int = 5) -> str:
    """Get recent pipeline/build status for a repository.

    Args:
        repo_slug: Repository slug (e.g., 'emvio-payment-service')
        limit: Number of recent pipelines to return
    """
    if not BITBUCKET_TOKEN:
        return "Error: CVE_BB_TOKEN environment variable not set."

    import requests

    try:
        url = f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}/{repo_slug}/pipelines/"
        params = {"pagelen": limit, "sort": "-created_on"}

        response = requests.get(url, auth=(BITBUCKET_EMAIL, BITBUCKET_TOKEN), params=params)

        if response.status_code != 200:
            return f"Error fetching pipelines: {response.status_code}"

        data = response.json()
        pipelines = data.get("values", [])

        if not pipelines:
            return f"No pipelines found for {repo_slug}"

        results = [f"Recent pipelines for {repo_slug}:"]
        for pipe in pipelines:
            state = pipe.get("state", {}).get("name", "Unknown")
            result = pipe.get("state", {}).get("result", {}).get("name", "")
            branch = pipe.get("target", {}).get("ref_name", "N/A")
            created = pipe.get("created_on", "")[:16].replace("T", " ")
            build_num = pipe.get("build_number", "")

            status = f"{state}"
            if result:
                status = result

            emoji = {"SUCCESSFUL": "OK", "FAILED": "FAIL", "RUNNING": "RUN"}.get(status, status)

            results.append(f"  #{build_num} [{emoji}] {branch} - {created}")

        return "\n".join(results)

    except Exception as e:
        return f"Error: {e}"


# ============================================================================
# EXPORT
# ============================================================================

BITBUCKET_TOOLS = [
    # Knowledge Base tools (semantic code search)
    search_code,
    search_code_in_repo,
    ask_about_code,
    find_file,
    list_indexed_repositories,
    get_knowledge_base_status,
    # Bitbucket API tools
    list_pull_requests,
    get_pipeline_status,
]

SYSTEM_PROMPT = """You are a Code Search Assistant for the MrRobot development team.

You have access to a Knowledge Base containing all code from MrRobot's repositories,
indexed using AWS Bedrock with semantic embeddings.

PRIMARY TOOLS (Semantic Code Search):
1. search_code - Search ALL repos using natural language
   Example: "CSP configuration", "S3 upload handler", "authentication middleware"

2. search_code_in_repo - Search within a specific repository
   Example: search_code_in_repo("CSP config", "emvio-dashboard-app")

3. ask_about_code - Get AI-generated answers about the codebase
   Example: "How is file upload implemented in the dashboard?"

4. find_file - Find files by name
   Example: "serverless.yml", "next.config"

5. list_indexed_repositories - See all indexed repos

6. get_knowledge_base_status - Check KB configuration

SECONDARY TOOLS (Bitbucket API):
7. list_pull_requests - List PRs from Bitbucket
8. get_pipeline_status - Check CI/CD pipeline status

TIPS:
- Use semantic search for configuration questions (CSP, CORS, env vars)
- Use ask_about_code for "how does X work?" questions
- Search by concept, not just keywords
- For specific files, use find_file first

Example interactions:
- "Where is CSP configured?" -> search_code("Content Security Policy configuration")
- "How do uploads work?" -> ask_about_code("How is file upload implemented?")
- "Find serverless configs" -> find_file("serverless.yml")
"""


def create_bitbucket_agent():
    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-west-2")
    return Agent(model=model, tools=BITBUCKET_TOOLS, system_prompt=SYSTEM_PROMPT)


bitbucket_agent = None  # Lazy initialization
