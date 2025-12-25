"""Slack Bot integration for DevOps MCP Server.

Runs alongside the MCP server to handle Slack messages and route them
to the appropriate MCP tools.

Architecture: Claude Tool Use
- User message -> Claude with tool definitions
- Claude decides which tool(s) to call
- Tool executes -> Claude summarizes results
- No hardcoded intent classification or regex patterns

Uses Socket Mode for connection (no public endpoint needed).

This file re-exports the modular components from the slack_bot/ package.
The actual implementation is split across:
- slack_bot/metrics.py: Request tracking and statistics
- slack_bot/alerting.py: Error alerting to dev channel
- slack_bot/bedrock_client.py: AWS Bedrock client wrapper
- slack_bot/prompt_enhancer.py: AI-powered prompt enhancement
- slack_bot/tool_executor.py: Tool execution and result compaction
- slack_bot/claude_tools.py: Claude Tool Use integration
- slack_bot/formatters.py: Response formatting for Slack
- slack_bot/bot.py: Main SlackBot class
"""

# Re-export everything from the package for backwards compatibility
from src.mcp_server.slack_bot import (
    CLIPPY_FOOTER,
    CLIPPY_INTRO,
    ClippyMetrics,
    SlackBot,
    alert_error,
    convert_to_slack_markdown,
    enhance_prompt,
    execute_tool,
    get_acknowledgment,
    get_bedrock_client,
    get_channel_info,
    get_metrics,
    get_thread_context,
    invoke_claude_with_tools,
    redact_secrets,
)

__all__ = [
    # Main classes
    "SlackBot",
    "ClippyMetrics",
    # Core functions
    "invoke_claude_with_tools",
    "execute_tool",
    "get_metrics",
    "get_bedrock_client",
    # Alerting
    "alert_error",
    # Prompt enhancement
    "enhance_prompt",
    # Formatters
    "convert_to_slack_markdown",
    "redact_secrets",
    "get_acknowledgment",
    "get_thread_context",
    "get_channel_info",
    "CLIPPY_INTRO",
    "CLIPPY_FOOTER",
]

# ============================================================================
# CLI ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Slack Bot for DevOps")
    parser.add_argument("--test", action="store_true", help="Run local tests")
    parser.add_argument("--start", action="store_true", help="Start the bot (requires tokens)")
    args = parser.parse_args()

    if args.test:
        print("=" * 60)
        print("SLACK BOT LOCAL TESTING")
        print("=" * 60)
        print("\nTests have been moved to tests/clippy_test_prompts.py")
        print("Run: python tests/clippy_test_prompts.py -i")
        print("=" * 60)
    elif args.start:
        bot = SlackBot()
        if bot.is_configured():
            print("Starting Slack bot...")
            bot.start(blocking=True)
        else:
            print("Slack tokens not configured. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN.")
    else:
        parser.print_help()
