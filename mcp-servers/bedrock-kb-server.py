#!/usr/bin/env python3
"""
MCP Server for Bedrock Knowledge Base
Supports both stdio (local) and SSE (remote) transports.

Local usage:  python bedrock-kb-server.py
Remote usage: python bedrock-kb-server.py --sse --port 8080
"""
import argparse
import json
import os
import sys

import boto3
import requests

# Configuration
KB_ID = os.environ.get("CODE_KB_ID", "SAJJWYFTNG")
REGION = os.environ.get("AWS_REGION", "us-east-1")
# Only use profile if explicitly set; otherwise use default credential chain (IAM roles on EC2)
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")

# Bitbucket configuration
BITBUCKET_EMAIL = os.environ.get("BITBUCKET_EMAIL", "gstarkman@nex.io")
BITBUCKET_WORKSPACE = "mrrobot-labs"
SECRETS_NAME = "mrrobot-ai-core/secrets"


def get_secrets():
    """Fetch secrets from AWS Secrets Manager with timeout."""
    from botocore.config import Config

    try:
        config = Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 1})
        if AWS_PROFILE:
            session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
        else:
            session = boto3.Session(region_name=REGION)
        client = session.client("secretsmanager", config=config)
        response = client.get_secret_value(SecretId=SECRETS_NAME)
        print(f"Successfully loaded secrets from {SECRETS_NAME}")
        return json.loads(response["SecretString"])
    except Exception as e:
        print(f"Warning: Could not fetch secrets from Secrets Manager: {e}")
        return {}


# Lazy load secrets (only when needed)
_secrets = None
_bitbucket_token = None


def get_bitbucket_token():
    """Get Bitbucket token, loading from Secrets Manager if needed."""
    global _secrets, _bitbucket_token
    if _bitbucket_token is not None:
        return _bitbucket_token

    # Check env var first
    _bitbucket_token = os.environ.get("CVE_BB_TOKEN", "")
    if _bitbucket_token:
        return _bitbucket_token

    # Try Secrets Manager
    if _secrets is None:
        _secrets = get_secrets()
    _bitbucket_token = _secrets.get("BITBUCKET_TOKEN", "")
    return _bitbucket_token


def search_knowledge_base(query: str, num_results: int = 5) -> dict:
    """Search the Bedrock Knowledge Base."""
    from botocore.config import Config

    # Add timeout configuration to prevent hanging
    config = Config(connect_timeout=10, read_timeout=25, retries={"max_attempts": 1})

    if AWS_PROFILE:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
    else:
        session = boto3.Session(region_name=REGION)
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
            # Extract repo/file from s3://bucket/repos/repo-name/path/file
            if "/repos/" in location:
                path = location.split("/repos/")[1]
            else:
                path = location

            # Extract repo name from path
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
    token = get_bitbucket_token()
    if not token:
        return {"error": "BITBUCKET_TOKEN not configured on server"}

    try:
        url = f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}/{repo}/src/{branch}/{file_path}"

        response = requests.get(url, auth=(BITBUCKET_EMAIL, token), timeout=30)

        if response.status_code == 404:
            return {"error": f"File not found: {repo}/{file_path}"}
        elif response.status_code != 200:
            return {"error": f"Bitbucket API error: {response.status_code}"}

        content = response.text

        # Limit content size for very large files
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


def get_tools_list():
    """Return the list of available tools."""
    return [
        {
            "name": "search_mrrobot_repos",
            "description": "REQUIRED for any MrRobot codebase questions. Searches ALL 254 MrRobot Bitbucket repositories (17,000+ files) using AI semantic search. Use this INSTEAD of local file search for questions about: CSP, CORS, authentication, S3, Lambda, serverless configs, dashboard code, cast-core, emvio services, payment processing, merchant APIs, or any MrRobot infrastructure. Returns matching code snippets with file paths and relevance scores.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g., 'Content Security Policy headers', 'S3 file upload', 'authentication middleware', 'CORS configuration')",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_in_repo",
            "description": "Search within a SPECIFIC MrRobot repository. Use when you know which repo to search (e.g., 'mrrobot-auth-rest', 'cast-core', 'emvio-gateway'). More focused than search_mrrobot_repos.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "repo_name": {
                        "type": "string",
                        "description": "Repository name to search in (e.g., 'mrrobot-auth-rest', 'cast-core')",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5,
                    },
                },
                "required": ["query", "repo_name"],
            },
        },
        {
            "name": "find_similar_code",
            "description": "Find code similar to a given snippet. Paste in code and find similar patterns across all MrRobot repositories.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code_snippet": {"type": "string", "description": "Code snippet to find similar patterns for"},
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5,
                    },
                },
                "required": ["code_snippet"],
            },
        },
        {
            "name": "get_kb_info",
            "description": "Get information about the MrRobot code knowledge base - how many repos, what's indexed, when last updated.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_file_content",
            "description": "Fetch the FULL content of a file from Bitbucket. Use after search_mrrobot_repos to get complete file contents. Requires repo name and file path.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name (e.g., 'mrrobot-rest-utils-npm', 'cast-core')",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file within the repo (e.g., 'src/index.js', 'serverless.yml')",
                    },
                    "branch": {"type": "string", "description": "Branch name (default: 'master')", "default": "master"},
                },
                "required": ["repo", "file_path"],
            },
        },
        {
            "name": "list_repos",
            "description": "List all MrRobot repositories in the knowledge base. Use to discover available repos or find repos by name pattern.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional filter pattern (e.g., 'cast', 'emvio', 'lambda')",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "search_by_file_type",
            "description": "Search for code patterns in specific file types only. Useful for finding configs, terraform, serverless files, etc.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "file_type": {
                        "type": "string",
                        "description": "File extension or type (e.g., 'serverless.yml', '.tf', '.js', 'package.json')",
                    },
                    "num_results": {"type": "integer", "description": "Number of results (default: 5)", "default": 5},
                },
                "required": ["query", "file_type"],
            },
        },
    ]


def handle_request(request: dict) -> dict:
    """Handle MCP protocol requests."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bedrock-kb", "version": "1.0.0"},
            },
        }

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": get_tools_list()}}

    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "search_mrrobot_repos":
            result = search_knowledge_base(query=args.get("query", ""), num_results=args.get("num_results", 5))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

        elif tool_name == "search_in_repo":
            # Search with repo context to help semantic search
            repo_name = args.get("repo_name", "")
            query = args.get("query", "")
            # Include repo name naturally in query for better semantic matching
            combined_query = f"{query} in {repo_name}"
            # Request more results since we'll filter
            result = search_knowledge_base(query=combined_query, num_results=min(args.get("num_results", 5) * 3, 15))
            # Filter results to only include the specified repo
            if "results" in result:
                filtered = [r for r in result["results"] if repo_name.lower() in r.get("repo", "").lower()]
                result["results"] = filtered[: args.get("num_results", 5)]
            result["repo_filter"] = repo_name
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

        elif tool_name == "find_similar_code":
            # Use code snippet as search query to find similar patterns
            code_snippet = args.get("code_snippet", "")
            result = search_knowledge_base(query=code_snippet, num_results=args.get("num_results", 5))
            result["search_type"] = "similar_code"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

        elif tool_name == "get_kb_info":
            result = {
                "knowledge_base_id": KB_ID,
                "region": REGION,
                "stats": {
                    "repositories": 254,
                    "documents_indexed": 17169,
                    "embedding_model": "amazon.titan-embed-text-v2:0",
                    "vector_store": "OpenSearch Serverless",
                },
                "available_tools": [t["name"] for t in get_tools_list()],
                "tips": [
                    "Use natural language queries - semantic search understands intent",
                    "Be specific: 'JWT validation in gateway' beats 'authentication'",
                    "Use find_similar_code to find patterns matching your code",
                    "Use search_in_repo when you know which repo to search",
                ],
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

        elif tool_name == "get_file_content":
            repo = args.get("repo", "")
            file_path = args.get("file_path", "")
            branch = args.get("branch", "master")

            result = get_file_from_bitbucket(repo, file_path, branch)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

        elif tool_name == "list_repos":
            filter_pattern = args.get("filter", "").lower()
            # Comprehensive list of known repos (sample - full 254 repos in KB)
            all_repos = [
                # Cast integrations
                "cast-core",
                "cast-quickbooks",
                "cast-housecallpro",
                "cast-jobber",
                "cast-service-titan",
                "cast-xero",
                "cast-databases",
                "cast-support-portal-service",
                "cast-dashboard",
                "cast-api",
                # MrRobot services
                "mrrobot-auth-rest",
                "mrrobot-rest-utils-npm",
                "mrrobot-common-js-utils",
                "mrrobot-sdk",
                "mrrobot-connector-hub",
                "mrrobot-key-rotation",
                "mrrobot-risk-rest",
                "mrrobot-merchant-onboarding-app",
                "mrrobot-confluence-sgupdater",
                "mrrobot-logging-lambda",
                "mrrobot-crowdstrike-logs-sync-lambda",
                "mrrobot-media-cdn",
                "mrrobot-azuread-last-login",
                "mrrobot-pii-npm",
                "mrrobot-secrets-npm",
                "mrrobot-ai-core",
                # Emvio services
                "emvio-gateway",
                "emvio-dashboard-app",
                "emvio-payment-service",
                "emvio-auth-service",
                "emvio-user-mgt-service",
                "emvio-transactions-service",
                "emvio-webhook-service",
                "emvio-scripts",
                "emvio-ui",
                "emvio-developer-tools",
                "emvio-tutorials",
                "emvio-proxy-tokenization-service",
                # Infrastructure
                "aws-terraform",
                "bitbucket-terraform",
                "bastion-ec2-ami",
                "devops-scripts",
                "pci-file-scanner",
                "freshdesk",
                "AWS-utility",
                "payment-testing-service-deployment",
            ]
            if filter_pattern:
                repos = [r for r in all_repos if filter_pattern in r.lower()]
            else:
                repos = all_repos

            result = {
                "total_indexed": 254,
                "matching_repos": repos,
                "count": len(repos),
                "filter": filter_pattern if filter_pattern else "none",
                "note": "This is a curated sample. Use search_mrrobot_repos to find code in any of the 254 indexed repos.",
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

        elif tool_name == "search_by_file_type":
            query = args.get("query", "")
            file_type = args.get("file_type", "")
            # Include file type in the search query
            enhanced_query = f"file:{file_type} {query}"
            result = search_knowledge_base(query=enhanced_query, num_results=args.get("num_results", 5))
            # Filter results to only include matching file types
            if "results" in result:
                result["results"] = [r for r in result["results"] if file_type.lower() in r.get("file", "").lower()]
            result["file_type_filter"] = file_type
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def run_stdio():
    """Run MCP server using stdio transport (local)."""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line)
            response = handle_request(request)

            if response:  # Don't send response for notifications
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


def run_sse(host: str, port: int):
    """Run MCP server using SSE transport (remote)."""
    import queue
    import uuid

    from flask import Flask, Response, jsonify, request

    app = Flask(__name__)

    # Store client connections and their message queues
    clients = {}

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "kb_id": KB_ID})

    @app.route("/sse", methods=["GET"])
    def sse_connect():
        """SSE endpoint for MCP clients - implements MCP SSE transport."""
        client_id = str(uuid.uuid4())
        # Capture the base URL from the request for use in the generator
        base_url = request.url_root.rstrip("/")

        def event_stream():
            q = queue.Queue()
            clients[client_id] = q

            # Send the endpoint event first (MCP SSE protocol requirement)
            # This tells the client where to POST messages
            # Use absolute URL as required by MCP SSE spec
            endpoint_url = f"{base_url}/message?session_id={client_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"

            try:
                while True:
                    try:
                        message = q.get(timeout=30)
                        yield f"event: message\ndata: {json.dumps(message)}\n\n"
                    except queue.Empty:
                        # Send keepalive comment
                        yield f": keepalive\n\n"
            finally:
                clients.pop(client_id, None)

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/message", methods=["POST", "OPTIONS"])
    def handle_message():
        """Handle incoming MCP JSON-RPC messages."""
        # Handle CORS preflight
        if request.method == "OPTIONS":
            return Response(
                "",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )

        try:
            session_id = request.args.get("session_id")
            data = request.get_json()
            response = handle_request(data)

            # If client has SSE connection, also push response there
            if session_id and session_id in clients:
                if response:
                    clients[session_id].put(response)

            if response:
                return jsonify(response), 200, {"Access-Control-Allow-Origin": "*"}
            return "", 204, {"Access-Control-Allow-Origin": "*"}
        except Exception as e:
            error_response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            return jsonify(error_response), 500, {"Access-Control-Allow-Origin": "*"}

    print(f"Starting MCP server on http://{host}:{port}")
    print(f"Knowledge Base ID: {KB_ID}")
    print(f"SSE endpoint: http://{host}:{port}/sse")
    print(f"Message endpoint: http://{host}:{port}/message")

    app.run(host=host, port=port, threaded=True)


def main():
    parser = argparse.ArgumentParser(description="MCP Server for Bedrock Knowledge Base")
    parser.add_argument("--sse", action="store_true", help="Run as SSE server instead of stdio")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE server (default: 8080)")
    args = parser.parse_args()

    if args.sse:
        run_sse(args.host, args.port)
    else:
        run_stdio()


if __name__ == "__main__":
    main()
