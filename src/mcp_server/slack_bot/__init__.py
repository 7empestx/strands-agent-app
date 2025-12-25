"""Slack Bot package for Clippy DevOps assistant.

This package contains the modular components of the Slack bot:
- metrics: Request tracking and statistics
- alerting: Error alerting to dev channel
- bedrock_client: AWS Bedrock client wrapper
- prompt_enhancer: AI-powered prompt enhancement
- tool_executor: Tool execution and result compaction
- claude_tools: Claude Tool Use integration
- formatters: Response formatting for Slack
- bot: Main SlackBot class
"""

from src.mcp_server.slack_bot.alerting import alert_error, get_slack_client, set_slack_client
from src.mcp_server.slack_bot.bedrock_client import get_bedrock_client
from src.mcp_server.slack_bot.bot import SlackBot
from src.mcp_server.slack_bot.claude_tools import invoke_claude_with_tools
from src.mcp_server.slack_bot.formatters import (
    CLIPPY_FOOTER,
    CLIPPY_INTRO,
    convert_to_slack_markdown,
    get_acknowledgment,
    get_channel_info,
    get_thread_context,
    redact_secrets,
)
from src.mcp_server.slack_bot.metrics import ClippyMetrics, get_metrics
from src.mcp_server.slack_bot.prompt_enhancer import enhance_prompt, enhance_prompt_with_ai
from src.mcp_server.slack_bot.tool_executor import execute_tool

__all__ = [
    # Main classes
    "SlackBot",
    "ClippyMetrics",
    # Core functions
    "invoke_claude_with_tools",
    "execute_tool",
    "get_metrics",
    # Bedrock
    "get_bedrock_client",
    # Alerting
    "alert_error",
    "get_slack_client",
    "set_slack_client",
    # Prompt enhancement
    "enhance_prompt",
    "enhance_prompt_with_ai",
    # Formatters
    "convert_to_slack_markdown",
    "redact_secrets",
    "get_acknowledgment",
    "get_thread_context",
    "get_channel_info",
    "CLIPPY_INTRO",
    "CLIPPY_FOOTER",
]
