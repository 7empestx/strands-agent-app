"""WebSocket Chatbot for Clippy Dashboard.

Provides a streaming chat interface using Claude Tool Use architecture.
Reuses the same tools as the Slack bot but streams responses via WebSocket.
"""

import asyncio
import json
import os
import sys
import time

from starlette.websockets import WebSocket, WebSocketDisconnect

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.lib.config_loader import get_system_prompt
from src.mcp_server.clippy_tools import CLIPPY_TOOLS
from src.mcp_server.slack_bot.bedrock_client import get_bedrock_client
from src.mcp_server.slack_bot.memory import add_context_from_memory
from src.mcp_server.slack_bot.prompt_enhancer import enhance_prompt
from src.mcp_server.slack_bot.tool_executor import execute_tool

# Model configuration
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
MAX_TOKENS = 4096
MAX_TOOL_CALLS = 10


class ChatSession:
    """Represents a chat session with message history."""

    def __init__(self, user_id: str = None, user_email: str = None):
        self.user_id = user_id
        self.user_email = user_email
        self.messages = []  # Claude API message format
        self.created_at = time.time()

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        """Add an assistant message to history."""
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_use(self, tool_use_block: dict):
        """Add a tool use block (assistant turn)."""
        # If last message is assistant, append to it
        if self.messages and self.messages[-1]["role"] == "assistant":
            if isinstance(self.messages[-1]["content"], str):
                self.messages[-1]["content"] = [{"type": "text", "text": self.messages[-1]["content"]}]
            self.messages[-1]["content"].append(tool_use_block)
        else:
            self.messages.append({"role": "assistant", "content": [tool_use_block]})

    def add_tool_result(self, tool_use_id: str, result: str):
        """Add a tool result (user turn)."""
        self.messages.append(
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result}],
            }
        )

    def get_messages(self, limit: int = 20) -> list:
        """Get recent messages for context."""
        return self.messages[-limit:]


# Active sessions (in production, use Redis)
_sessions: dict[str, ChatSession] = {}


def get_or_create_session(session_id: str, user_id: str = None, user_email: str = None) -> ChatSession:
    """Get existing session or create new one."""
    if session_id not in _sessions:
        _sessions[session_id] = ChatSession(user_id, user_email)
    return _sessions[session_id]


async def handle_chat_websocket(websocket: WebSocket):
    """Handle WebSocket chat connection."""
    await websocket.accept()

    # Get user from auth (if available)
    user = getattr(websocket.state, "user", None) if hasattr(websocket, "state") else None
    user_id = user.get("sub") if user else "anonymous"
    user_email = user.get("email") if user else None

    # Create or get session
    session_id = f"{user_id}_{int(time.time())}"
    session = get_or_create_session(session_id, user_id, user_email)

    print(f"[Chat] WebSocket connected: {user_email or 'anonymous'}")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data.get("type") == "message":
                content = message_data.get("content", "").strip()
                if content:
                    await process_chat_message(websocket, session, content)

            elif message_data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        print(f"[Chat] WebSocket disconnected: {user_email or 'anonymous'}")
    except Exception as e:
        print(f"[Chat] WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def process_chat_message(websocket: WebSocket, session: ChatSession, message: str):
    """Process a chat message and stream the response."""
    start_time = time.time()

    # Send acknowledgment
    await websocket.send_json({"type": "status", "status": "thinking"})

    # Enhance the message with context
    enhanced_message = enhance_prompt(message)

    # Extract service for memory lookup
    detected_service = None
    if "Services:" in enhanced_message:
        try:
            services_line = [line for line in enhanced_message.split("\n") if "Services:" in line][0]
            detected_service = services_line.split("Services:")[1].strip().split(",")[0].strip()
        except Exception:
            pass

    # Add memory context
    if detected_service:
        enhanced_message = add_context_from_memory(enhanced_message, detected_service, None)

    # Add to session
    session.add_user_message(enhanced_message)

    # Get system prompt
    system_prompt = get_system_prompt()

    # Call Claude with streaming
    try:
        await stream_claude_response(websocket, session, system_prompt)
    except Exception as e:
        print(f"[Chat] Error: {e}")
        await websocket.send_json({"type": "error", "message": f"Error: {str(e)}"})

    elapsed = time.time() - start_time
    print(f"[Chat] Response completed in {elapsed:.2f}s")


async def stream_claude_response(websocket: WebSocket, session: ChatSession, system_prompt: str):
    """Stream Claude response with tool handling."""
    client = get_bedrock_client()
    tool_iterations = 0

    while tool_iterations < MAX_TOOL_CALLS:
        # Prepare request body
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "messages": session.get_messages(),
            "tools": CLIPPY_TOOLS,
        }

        # Call Bedrock with streaming
        response = client.invoke_model_with_response_stream(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )

        # Process stream
        accumulated_text = ""
        tool_use_blocks = []
        current_tool_use = None
        stop_reason = None

        for event in response.get("body", []):
            chunk = json.loads(event["chunk"]["bytes"])

            if chunk["type"] == "content_block_start":
                block = chunk.get("content_block", {})
                if block.get("type") == "tool_use":
                    current_tool_use = {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": "",
                    }
                    # Notify client about tool start
                    await websocket.send_json(
                        {
                            "type": "tool_start",
                            "name": block.get("name"),
                            "id": block.get("id"),
                        }
                    )

            elif chunk["type"] == "content_block_delta":
                delta = chunk.get("delta", {})

                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    accumulated_text += text
                    # Stream token to client
                    await websocket.send_json({"type": "token", "content": text})

                elif delta.get("type") == "input_json_delta":
                    if current_tool_use:
                        current_tool_use["input"] += delta.get("partial_json", "")

            elif chunk["type"] == "content_block_stop":
                if current_tool_use:
                    # Parse the accumulated JSON input
                    try:
                        current_tool_use["input"] = json.loads(current_tool_use["input"])
                    except json.JSONDecodeError:
                        current_tool_use["input"] = {}
                    tool_use_blocks.append(current_tool_use)
                    current_tool_use = None

            elif chunk["type"] == "message_delta":
                stop_reason = chunk.get("delta", {}).get("stop_reason")

        # Add assistant response to session
        if accumulated_text:
            session.add_assistant_message(accumulated_text)
        for tool_block in tool_use_blocks:
            session.add_tool_use(tool_block)

        # If stopped due to tool use, execute tools and continue
        if stop_reason == "tool_use" and tool_use_blocks:
            tool_iterations += 1

            for tool_block in tool_use_blocks:
                tool_name = tool_block["name"]
                tool_input = tool_block["input"]
                tool_id = tool_block["id"]

                # Execute tool
                await websocket.send_json(
                    {
                        "type": "tool_executing",
                        "name": tool_name,
                        "input": tool_input,
                    }
                )

                # Run tool in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                tool_result = await loop.run_in_executor(None, lambda: execute_tool(tool_name, tool_input))

                # Compact result to avoid token overflow
                result_str = json.dumps(tool_result, default=str)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... (truncated)"

                # Add tool result to session
                session.add_tool_result(tool_id, result_str)

                # Notify client
                await websocket.send_json(
                    {
                        "type": "tool_end",
                        "name": tool_name,
                        "id": tool_id,
                    }
                )

            # Continue loop to get Claude's response to tool results
            continue

        # No more tools to call, we're done
        break

    # Send completion
    await websocket.send_json({"type": "done"})
