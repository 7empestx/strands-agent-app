#!/usr/bin/env python3
"""
MCP Server for Bedrock Knowledge Base
Supports both stdio (local) and SSE (remote) transports.

Local usage:  python bedrock-kb-server.py
Remote usage: python bedrock-kb-server.py --sse --port 8080
"""
import json
import sys
import os
import argparse
import boto3
from typing import Any

# Configuration
KB_ID = os.environ.get("CODE_KB_ID", "SAJJWYFTNG")
REGION = os.environ.get("AWS_REGION", "us-east-1")
# Only use profile if explicitly set; otherwise use default credential chain (IAM roles on EC2)
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")


def search_knowledge_base(query: str, num_results: int = 5) -> dict:
    """Search the Bedrock Knowledge Base."""
    if AWS_PROFILE:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
    else:
        session = boto3.Session(region_name=REGION)
    client = session.client("bedrock-agent-runtime")

    try:
        response = client.retrieve(
            knowledgeBaseId=KB_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": num_results
                }
            }
        )

        results = []
        for item in response.get("retrievalResults", []):
            location = item.get("location", {}).get("s3Location", {}).get("uri", "")
            # Extract repo/file from s3://bucket/repos/repo-name/path/file
            if "/repos/" in location:
                path = location.split("/repos/")[1]
            else:
                path = location

            results.append({
                "file": path,
                "score": round(item.get("score", 0), 3),
                "content": item.get("content", {}).get("text", "")[:500]
            })

        return {"results": results, "query": query}
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
                        "description": "Natural language search query (e.g., 'Content Security Policy headers', 'S3 file upload', 'authentication middleware', 'CORS configuration')"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "search_in_repo",
            "description": "Search within a SPECIFIC MrRobot repository. Use when you know which repo to search (e.g., 'mrrobot-auth-rest', 'cast-core', 'emvio-gateway'). More focused than search_mrrobot_repos.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query"
                    },
                    "repo_name": {
                        "type": "string",
                        "description": "Repository name to search in (e.g., 'mrrobot-auth-rest', 'cast-core')"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5
                    }
                },
                "required": ["query", "repo_name"]
            }
        },
        {
            "name": "find_similar_code",
            "description": "Find code similar to a given snippet. Paste in code and find similar patterns across all MrRobot repositories.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code_snippet": {
                        "type": "string",
                        "description": "Code snippet to find similar patterns for"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5
                    }
                },
                "required": ["code_snippet"]
            }
        }
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
                "serverInfo": {"name": "bedrock-kb", "version": "1.0.0"}
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": get_tools_list()}
        }

    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "search_mrrobot_repos":
            result = search_knowledge_base(
                query=args.get("query", ""),
                num_results=args.get("num_results", 5)
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }

        elif tool_name == "search_in_repo":
            # Search with repo name in query to filter results
            repo_name = args.get("repo_name", "")
            query = args.get("query", "")
            combined_query = f"repository:{repo_name} {query}"
            result = search_knowledge_base(
                query=combined_query,
                num_results=args.get("num_results", 5)
            )
            # Filter results to only include the specified repo
            if "results" in result:
                result["results"] = [
                    r for r in result["results"]
                    if repo_name.lower() in r.get("file", "").lower()
                ]
            result["repo_filter"] = repo_name
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }

        elif tool_name == "find_similar_code":
            # Use code snippet as search query to find similar patterns
            code_snippet = args.get("code_snippet", "")
            result = search_knowledge_base(
                query=code_snippet,
                num_results=args.get("num_results", 5)
            )
            result["search_type"] = "similar_code"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }


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
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


def run_sse(host: str, port: int):
    """Run MCP server using SSE transport (remote)."""
    from flask import Flask, Response, request, jsonify
    import queue
    import uuid

    app = Flask(__name__)

    # Store client connections and their message queues
    clients = {}

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok", "kb_id": KB_ID})

    @app.route('/sse', methods=['GET'])
    def sse_connect():
        """SSE endpoint for MCP clients - implements MCP SSE transport."""
        client_id = str(uuid.uuid4())
        # Capture the base URL from the request for use in the generator
        base_url = request.url_root.rstrip('/')

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
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'X-Accel-Buffering': 'no'
            }
        )

    @app.route('/message', methods=['POST', 'OPTIONS'])
    def handle_message():
        """Handle incoming MCP JSON-RPC messages."""
        # Handle CORS preflight
        if request.method == 'OPTIONS':
            return Response('', headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            })

        try:
            session_id = request.args.get('session_id')
            data = request.get_json()
            response = handle_request(data)

            # If client has SSE connection, also push response there
            if session_id and session_id in clients:
                if response:
                    clients[session_id].put(response)

            if response:
                return jsonify(response), 200, {
                    'Access-Control-Allow-Origin': '*'
                }
            return '', 204, {'Access-Control-Allow-Origin': '*'}
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            return jsonify(error_response), 500, {
                'Access-Control-Allow-Origin': '*'
            }

    print(f"Starting MCP server on http://{host}:{port}")
    print(f"Knowledge Base ID: {KB_ID}")
    print(f"SSE endpoint: http://{host}:{port}/sse")
    print(f"Message endpoint: http://{host}:{port}/message")

    app.run(host=host, port=port, threaded=True)


def main():
    parser = argparse.ArgumentParser(description='MCP Server for Bedrock Knowledge Base')
    parser.add_argument('--sse', action='store_true', help='Run as SSE server instead of stdio')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='Port for SSE server (default: 8080)')
    args = parser.parse_args()

    if args.sse:
        run_sse(args.host, args.port)
    else:
        run_stdio()


if __name__ == "__main__":
    main()
