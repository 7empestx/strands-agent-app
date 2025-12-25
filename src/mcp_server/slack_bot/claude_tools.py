"""Claude Tool Use integration for Clippy.

Handles the core Claude API interaction with tool definitions and multi-turn
tool calling loop.
"""

import json
import time

from src.lib.config_loader import get_system_prompt
from src.mcp_server.clippy_tools import CLIPPY_TOOLS
from src.mcp_server.slack_bot.alerting import alert_error
from src.mcp_server.slack_bot.bedrock_client import get_bedrock_client
from src.mcp_server.slack_bot.memory import add_context_from_memory
from src.mcp_server.slack_bot.metrics import get_metrics
from src.mcp_server.slack_bot.prompt_enhancer import enhance_prompt
from src.mcp_server.slack_bot.tool_executor import execute_tool


def invoke_claude_with_tools(
    message: str,
    thread_context: list = None,
    max_tokens: int = 600,
    max_tool_calls: int = 10,
    channel_info: dict = None,
) -> dict:
    """Invoke Claude with tool definitions and handle tool calls.

    This is the core of the Claude Tool Use architecture:
    1. Enhance the message with context (time, service info, env, channel)
    2. Send message to Claude with tool definitions
    3. If Claude wants to use a tool, execute it
    4. Send tool result back to Claude
    5. Repeat until Claude gives final response (up to max_tool_calls)

    Args:
        message: The user's message
        thread_context: Previous messages in the thread
        max_tokens: Max tokens for response
        max_tool_calls: Max tool iterations
        channel_info: Dict with 'name' and 'is_devops' from get_channel_info()

    Returns:
        dict with 'response' (text) and optionally 'tool_used', 'tool_result'
    """
    start_time = time.time()
    client = get_bedrock_client()
    metrics = get_metrics()
    any_truncated = False

    # Enhance the message with additional context
    enhanced_message = enhance_prompt(message)

    # Extract service/environment for memory lookup (from enhanced message)
    detected_service = None
    detected_env = None
    if "Services:" in enhanced_message:
        try:
            services_line = [line for line in enhanced_message.split("\n") if "Services:" in line][0]
            detected_service = services_line.split("Services:")[1].strip().split(",")[0].strip()
        except Exception:
            pass
    if "Environment:" in enhanced_message:
        try:
            env_line = [line for line in enhanced_message.split("\n") if "Environment:" in line][0]
            detected_env = env_line.split("Environment:")[1].strip().split()[0].lower()
        except Exception:
            pass

    # Add memory context if we have a service
    if detected_service:
        enhanced_message = add_context_from_memory(enhanced_message, detected_service, detected_env)

    # Add channel context if available
    if channel_info and channel_info.get("name"):
        channel_context = f"\n\n[Context: User is in #{channel_info['name']} channel"
        if channel_info.get("is_devops"):
            channel_context += " - this IS the DevOps channel, don't tell them to post here"
        channel_context += "]"
        enhanced_message += channel_context
    if enhanced_message != message:
        print(f"[Clippy] Prompt enhanced with context")

    # Build messages with optional thread context
    messages = []
    if thread_context:
        # Add thread context as assistant/user turns (last 10 messages for good context)
        for ctx in thread_context[-10:]:
            if ctx.startswith("Clippy:"):
                role = "assistant"
                content = ctx[8:]  # Remove "Clippy: " prefix
            else:
                role = "user"
                content = ctx[6:] if ctx.startswith("User: ") else ctx  # Remove "User: " prefix if present

            # Skip empty messages
            if content.strip():
                messages.append({"role": role, "content": content})

    # Add current message (with enhancements)
    messages.append({"role": "user", "content": enhanced_message})

    tools_used = []
    tool_results = []

    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": get_system_prompt(),  # Loaded from S3
            "messages": messages,
            "tools": CLIPPY_TOOLS,
        }

        # Loop for multi-turn tool calling
        for turn in range(max_tool_calls + 1):
            response = client.invoke_model(
                modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
                body=json.dumps(body),
            )

            result = json.loads(response["body"].read())
            stop_reason = result.get("stop_reason", "")
            content = result.get("content", [])

            print(f"[Clippy] Turn {turn + 1} - stop_reason: {stop_reason}, content blocks: {len(content)}")

            # If Claude is done (end_turn or max_tokens), extract final response
            if stop_reason != "tool_use":
                final_text = ""
                for block in content:
                    if block.get("type") == "text":
                        final_text += block.get("text", "")

                # Record metrics
                duration_ms = (time.time() - start_time) * 1000
                metrics.record_request(duration_ms, tools_used, any_truncated, hit_limit=False)
                if metrics.total_requests % 10 == 0:
                    metrics.log_summary()

                return {
                    "response": final_text or "I found some results but had trouble summarizing them.",
                    "tool_used": tools_used[-1] if tools_used else None,
                    "tool_result": tool_results[-1] if tool_results else None,
                    "all_tools_used": tools_used,
                    "was_truncated": any_truncated,
                }

            # Claude wants to use tool(s) - may be multiple in parallel
            tool_use_blocks = [block for block in content if block.get("type") == "tool_use"]

            if not tool_use_blocks:
                break

            # Check for respond_directly first
            for tool_use in tool_use_blocks:
                if tool_use.get("name") == "respond_directly":
                    return {
                        "response": tool_use.get("input", {}).get("message", "How can I help?"),
                        "tool_used": None,
                        "tool_result": None,
                    }

            # Execute all tools and collect results
            tool_result_contents = []
            for tool_use in tool_use_blocks:
                tool_name = tool_use.get("name")
                tool_input = tool_use.get("input", {})
                tool_id = tool_use.get("id")

                print(f"[Clippy] Tool call {turn + 1}: {tool_name}({tool_input})")

                # Execute the tool
                tool_result = execute_tool(tool_name, tool_input)
                tools_used.append(tool_name)
                tool_results.append(tool_result)

                # Serialize tool result and check if truncation needed
                tool_result_str = json.dumps(tool_result, default=str)
                was_truncated = len(tool_result_str) > 8000
                if was_truncated:
                    any_truncated = True
                    print(f"[Clippy] WARNING: {tool_name} result truncated from {len(tool_result_str)} to 8000 chars")
                    tool_result_str = (
                        tool_result_str[:7800]
                        + "\n\n[WARNING: Results truncated. There may be additional data not shown. Ask user to narrow their query if needed.]"
                    )

                tool_result_contents.append({"type": "tool_result", "tool_use_id": tool_id, "content": tool_result_str})

            # Add assistant's response and all tool results to messages
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": tool_result_contents})

            # Update body for next turn
            body["messages"] = messages
            body["max_tokens"] = 1200  # More tokens for summaries

        # If we hit max turns, return what we have
        print(f"[Clippy] WARNING: Hit max tool calls limit ({max_tool_calls}). Tools used: {tools_used}")
        duration_ms = (time.time() - start_time) * 1000
        metrics.record_request(duration_ms, tools_used, any_truncated, hit_limit=True)
        metrics.log_summary()

        return {
            "response": "I ran multiple searches but need more information to help fully. Here's what I found so far - could you provide more specific details about the issue?",
            "tool_used": tools_used[-1] if tools_used else None,
            "tool_result": tool_results[-1] if tool_results else None,
            "all_tools_used": tools_used,
            "was_truncated": any_truncated,
            "hit_tool_limit": True,
        }

    except Exception as e:
        print(f"[Clippy] Error in invoke_claude_with_tools: {e}")
        import traceback

        traceback.print_exc()

        # Record error metrics
        duration_ms = (time.time() - start_time) * 1000
        metrics.record_request(duration_ms, [], was_truncated=False, hit_limit=False, error=True)

        # Alert to dev channel
        alert_error(
            "Claude API Error",
            f"Error processing request: {str(e)[:200]}",
            {"message_preview": message[:100], "duration_ms": f"{duration_ms:.0f}"},
        )

        return {
            "response": f"I encountered an error: {str(e)[:100]}. Please try again.",
            "tool_used": None,
            "tool_result": None,
            "error": True,
        }
