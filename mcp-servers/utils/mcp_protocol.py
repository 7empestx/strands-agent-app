"""MCP JSON-RPC protocol helpers."""

import json
from typing import Any, Callable


def create_tool_result(req_id: Any, result: Any) -> dict:
    """Create a successful tool result response."""
    if isinstance(result, str):
        content = [{"type": "text", "text": result}]
    elif isinstance(result, dict):
        content = [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
    else:
        content = [{"type": "text", "text": str(result)}]

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"content": content},
    }


def create_error_response(req_id: Any, code: int, message: str) -> dict:
    """Create an error response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


class MCPProtocol:
    """MCP protocol handler with tool registration."""

    def __init__(self, server_name: str = "mrrobot-mcp", version: str = "2.0.0"):
        self.server_name = server_name
        self.version = version
        self.tools: dict[str, dict] = {}  # name -> {schema, handler}

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable,
    ):
        """Register a tool with its schema and handler."""
        self.tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
        }

    def get_tools_list(self) -> list:
        """Get list of tool schemas for tools/list response."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in self.tools.values()
        ]

    def handle_request(self, request: dict) -> dict | None:
        """Handle an MCP JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.server_name, "version": self.version},
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tools_list()},
            }

        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {})

            if tool_name not in self.tools:
                return create_error_response(req_id, -32601, f"Unknown tool: {tool_name}")

            try:
                handler = self.tools[tool_name]["handler"]
                result = handler(**args)
                return create_tool_result(req_id, result)
            except Exception as e:
                return create_error_response(req_id, -32603, f"Tool error: {str(e)}")

        elif method == "notifications/initialized":
            return None  # No response for notifications

        return create_error_response(req_id, -32601, f"Method not found: {method}")

