#!/usr/bin/env python3
"""
MrRobot MCP Server - Unified MCP server for all MrRobot tools.

Supports both stdio (local) and HTTP (remote) transports.

Local usage:  python server.py
Remote usage: python server.py --http --port 8080

Tools available:
- Code Search (Bedrock Knowledge Base)
- Coralogix Log Analysis
- Atlassian Admin (User/Group Management)
"""

import argparse
import json
import os
import queue
import sys
import uuid

from flask import Flask, Response, jsonify, request

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.mcp_protocol import MCPProtocol
from tools.bedrock_kb import register_bedrock_kb_tools
from tools.coralogix import register_coralogix_tools
from tools.atlassian import register_atlassian_tools

# Configuration
KB_ID = os.environ.get("CODE_KB_ID", "SAJJWYFTNG")


def create_protocol() -> MCPProtocol:
    """Create and configure the MCP protocol handler with all tools."""
    protocol = MCPProtocol(server_name="mrrobot-mcp", version="2.0.0")

    # Register all tool modules
    register_bedrock_kb_tools(protocol)
    register_coralogix_tools(protocol)
    register_atlassian_tools(protocol)

    print(f"[MCP] Registered {len(protocol.tools)} tools:")
    for name in sorted(protocol.tools.keys()):
        print(f"  - {name}")

    return protocol


def run_stdio(protocol: MCPProtocol):
    """Run MCP server using stdio transport (local)."""
    print("[MCP] Starting in stdio mode...")

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request_data = json.loads(line)
            response = protocol.handle_request(request_data)

            if response:  # Don't send response for notifications
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


def run_http(protocol: MCPProtocol, host: str, port: int):
    """Run MCP server using HTTP transport (remote).

    Supports both StreamableHTTP and SSE transports:
    - POST /sse: StreamableHTTP (preferred by Cursor)
    - GET /sse: SSE event stream (legacy)
    """
    app = Flask(__name__)

    # Store SSE client connections
    clients = {}

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "server": "mrrobot-mcp",
            "version": "2.0.0",
            "tools_count": len(protocol.tools),
            "kb_id": KB_ID,
            "transport": "streamable-http+sse",
        })

    @app.route("/tools", methods=["GET"])
    def list_tools():
        """Convenience endpoint to list all available tools."""
        tools = protocol.get_tools_list()
        return jsonify({
            "count": len(tools),
            "tools": [{"name": t["name"], "description": t["description"]} for t in tools],
        })

    @app.route("/sse", methods=["GET", "POST", "OPTIONS"])
    def sse_endpoint():
        """Combined endpoint for StreamableHTTP and SSE transports.

        - POST: StreamableHTTP - direct request/response (preferred)
        - GET: SSE - establish event stream for legacy clients
        - OPTIONS: CORS preflight
        """
        # CORS preflight
        if request.method == "OPTIONS":
            return Response(
                "",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Accept",
                },
            )

        # StreamableHTTP: POST with JSON-RPC request
        if request.method == "POST":
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON body"}), 400, {"Access-Control-Allow-Origin": "*"}

                response = protocol.handle_request(data)

                if response:
                    return jsonify(response), 200, {"Access-Control-Allow-Origin": "*"}
                return "", 204, {"Access-Control-Allow-Origin": "*"}
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                }
                return jsonify(error_response), 500, {"Access-Control-Allow-Origin": "*"}

        # SSE: GET to establish event stream
        client_id = str(uuid.uuid4())
        base_url = request.url_root.rstrip("/")

        def event_stream():
            q = queue.Queue()
            clients[client_id] = q

            # Send endpoint event (MCP SSE protocol requirement)
            endpoint_url = f"{base_url}/message?session_id={client_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"

            try:
                while True:
                    try:
                        message = q.get(timeout=30)
                        yield f"event: message\ndata: {json.dumps(message)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
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
        """Handle incoming MCP JSON-RPC messages (for SSE transport)."""
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
            response = protocol.handle_request(data)

            # Push to SSE client if connected
            if session_id and session_id in clients:
                if response:
                    clients[session_id].put(response)

            if response:
                return jsonify(response), 200, {"Access-Control-Allow-Origin": "*"}
            return "", 204, {"Access-Control-Allow-Origin": "*"}
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }
            return jsonify(error_response), 500, {"Access-Control-Allow-Origin": "*"}

    print(f"[MCP] Starting HTTP server on http://{host}:{port}")
    print(f"[MCP] Health: http://{host}:{port}/health")
    print(f"[MCP] Tools: http://{host}:{port}/tools")
    print(f"[MCP] Transports: StreamableHTTP (POST /sse) + SSE (GET /sse)")

    app.run(host=host, port=port, threaded=True)


def main():
    parser = argparse.ArgumentParser(description="MrRobot MCP Server")
    parser.add_argument("--http", "--sse", action="store_true", help="Run as HTTP server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP server")
    args = parser.parse_args()

    protocol = create_protocol()

    if args.http:
        run_http(protocol, args.host, args.port)
    else:
        run_stdio(protocol)


if __name__ == "__main__":
    main()

