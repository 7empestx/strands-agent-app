"""SlackBot class for Clippy DevOps assistant.

Handles Slack event listeners, message routing, and bot lifecycle.
"""

import os
import re
import threading

from src.lib.utils.secrets import get_secret
from src.mcp_server.slack_bot.alerting import set_slack_client
from src.mcp_server.slack_bot.claude_tools import invoke_claude_with_tools
from src.mcp_server.slack_bot.feedback import record_feedback, store_message_for_feedback
from src.mcp_server.slack_bot.formatters import (
    CLIPPY_FOOTER,
    convert_to_slack_markdown,
    get_acknowledgment,
    get_channel_info,
    get_thread_context,
    redact_secrets,
)


class SlackBot:
    """Slack bot that routes messages to MCP tools.

    Auto-reply behavior:
    - Always responds to @mentions in any channel
    - Auto-replies to all new messages (once per thread) in AUTO_REPLY_CHANNELS (when enabled)
    - Configure via SLACK_AUTO_REPLY_CHANNELS env var (comma-separated channel IDs)
    - Toggle auto-reply via "@Clippy-ai auto-reply on/off"
    """

    # Channels where bot auto-replies to all messages (not just mentions)
    # Loaded from Secrets Manager or environment variable
    # Can be toggled at runtime via "@Clippy-ai auto-reply on/off"
    _auto_reply_enabled = False  # Global toggle - disabled by default, use @mention instead

    # Default channel for devops + any configured via secrets/env
    AUTO_REPLY_CHANNELS = {"C0A3RJA9LSJ"}  # Will be updated in __init__

    def __init__(self, bot_token: str = None, app_token: str = None):
        """Initialize the Slack bot.

        Args:
            bot_token: Slack bot token (xoxb-...) or fetched from secrets
            app_token: Slack app token (xapp-...) or fetched from secrets
        """
        self.bot_token = bot_token or get_secret("SLACK_BOT_TOKEN")
        self.app_token = app_token or get_secret("SLACK_APP_TOKEN")
        self.app = None
        self.handler = None

        # Load additional auto-reply channels from secrets/env
        channels_str = get_secret("SLACK_AUTO_REPLY_CHANNELS") or ""
        if not channels_str:
            channels_str = os.environ.get("SLACK_AUTO_REPLY_CHANNELS", "")
        if channels_str:
            SlackBot.AUTO_REPLY_CHANNELS.update(filter(None, channels_str.split(",")))
        self._thread = None
        self._responded_threads = set()  # Track threads we've already responded to
        self._bot_user_id = None  # Will be set on startup

    def is_configured(self) -> bool:
        """Check if Slack tokens are configured."""
        return bool(self.bot_token and self.app_token)

    def _setup_app(self):
        """Set up the Slack Bolt app with event handlers."""
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        self.app = App(token=self.bot_token)

        # Set global slack client for error alerting
        set_slack_client(self.app.client)

        @self.app.event("app_mention")
        def handle_mention(event, say, client):
            """Handle @mentions of the bot - uses Claude Tool Use."""
            text = event.get("text", "")
            channel = event["channel"]
            thread_ts = event.get("thread_ts") or event["ts"]
            user = event.get("user", "")

            # Remove bot mention from text
            text = re.sub(r"<@\w+>", "", text).strip()

            print(f"[Clippy] Mention from {user}: {text[:100]}")

            # Handle empty message
            if not text:
                say(
                    "Hi! I'm Clippy, your DevOps assistant. Try:\n"
                    "- `search logs for errors in prod`\n"
                    "- `check recent deploys for emvio-dashboard-app`\n"
                    "- `find CSP configuration in codebase`\n"
                    "- `list CloudWatch alarms`",
                    thread_ts=thread_ts,
                )
                return

            # Acknowledge immediately with context-aware message
            ack_msg = get_acknowledgment(text)
            say(ack_msg, thread_ts=thread_ts)

            # Fetch thread context for follow-up awareness
            thread_context = get_thread_context(client, channel, thread_ts)
            if thread_context:
                print(f"[Clippy] Thread context: {len(thread_context)} messages")

            # Get channel info so Claude knows where the user is
            channel_info = get_channel_info(client, channel)
            if channel_info.get("name"):
                print(f"[Clippy] Channel: #{channel_info['name']} (is_devops={channel_info['is_devops']})")

            # Use Claude Tool Use - Claude decides what to do
            result = invoke_claude_with_tools(text, thread_context, channel_info=channel_info)

            print(f"[Clippy] Tool used: {result.get('tool_used')}")

            # Format response with footer, convert markdown, and redact any secrets
            response = result.get("response", "I'm not sure how to help with that.")
            response = convert_to_slack_markdown(response)  # Convert **bold** to *bold*
            response = redact_secrets(response)
            # Only add footer if not already present (avoid duplicates)
            if "Clippy is a work in progress" not in response:
                response += CLIPPY_FOOTER

            # Reply in thread and store for feedback tracking
            msg_response = say(response, thread_ts=thread_ts)

            # Store message metadata for feedback correlation
            if msg_response and msg_response.get("ts"):
                store_message_for_feedback(
                    message_ts=msg_response["ts"],
                    channel=channel,
                    user_query=text,
                    tools_used=result.get("all_tools_used", []),
                    response_preview=response[:500],
                    duration_ms=result.get("duration_ms", 0),
                )

        @self.app.event("reaction_added")
        def handle_reaction(event, client):
            """Handle reactions on Clippy messages for feedback collection."""
            reaction = event.get("reaction", "")
            item = event.get("item", {})
            user = event.get("user", "")

            # Only track reactions on messages (not files, etc.)
            if item.get("type") != "message":
                return

            message_ts = item.get("ts", "")
            channel = item.get("channel", "")

            # Record the feedback
            record_feedback(
                message_ts=message_ts,
                reaction=reaction,
                user_id=user,
                channel=channel,
            )

        @self.app.command("/devops")
        def handle_command(ack, respond, command):
            """Handle /devops slash command - uses Claude Tool Use."""
            ack()
            text = command.get("text", "")
            user = command.get("user_id", "")

            print(f"[Clippy] Command from {user}: {text[:100]}")

            # Use Claude Tool Use
            result = invoke_claude_with_tools(text)
            response = result.get("response", "I'm not sure how to help with that.")
            response = convert_to_slack_markdown(response)  # Convert **bold** to *bold*
            response = redact_secrets(response)
            # Only add footer if not already present (avoid duplicates)
            if "Clippy is a work in progress" not in response:
                response += CLIPPY_FOOTER

            respond(response)

        @self.app.command("/clippy-help")
        def handle_help_command(ack, respond, command):
            """Handle /clippy-help slash command - shows Clippy's capabilities."""
            ack()

            help_text = """*:paperclip: Clippy Capabilities*

*Logs & Troubleshooting*
- `@Clippy check logs for errors in [service]` - Search Coralogix logs
- `@Clippy what's broken?` - Get recent errors across services
- `@Clippy investigate [service] in prod` - Full automated investigation

*Code Search*
- `@Clippy how does authentication work?` - Semantic code search across 254 repos
- `@Clippy find CSP configuration` - Find specific implementations

*Deployments & Pipelines*
- `@Clippy pipeline status for [repo]` - Recent builds/deploys
- `@Clippy why did build 123 fail in [repo]?` - Pipeline failure details

*Pull Requests*
- `@Clippy show open PRs in [repo]` - List open pull requests
- `@Clippy [paste Bitbucket PR URL]` - Get PR details and diff summary

*Jira Tickets*
- `@Clippy show me open CVE tickets` - Security vulnerability tickets
- `@Clippy tell me about DEVOPS-123` - Get ticket details
- `@Clippy find tickets with PCI label` - Search by label

*PagerDuty Incidents*
- `@Clippy show me active incidents` - Currently triggered/acknowledged
- `@Clippy incidents this week` - Recent incident history
- `@Clippy investigate incident PXXXXXX` - Full details + related logs

*AWS & CloudWatch*
- `@Clippy list alarms in ALARM state` - Check CloudWatch alarms
- `@Clippy search CloudWatch logs for [service]` - AWS log search
- `@Clippy check ECS metrics` - CPU/memory usage

*DevOps History*
- `@Clippy have we seen 504 errors before?` - Search past Slack conversations

*Example Queries:*
```
@Clippy cast-core is returning 504s in prod
@Clippy why did the emvio-dashboard-app deploy fail?
@Clippy show me CVE tickets assigned to me
@Clippy what changed in cast-core recently?
```

_Tip: Be specific with service names and environments for best results!_"""

            respond(help_text)

        @self.app.event("message")
        def handle_message(event, say, client):
            """Handle all messages - auto-reply once per thread in designated channels.

            Uses Claude Tool Use for AI-powered responses.
            Only responds to new parent messages, not thread replies (use @mention for follow-ups).
            """
            channel = event.get("channel", "")
            text = event.get("text", "")[:200] if event.get("text") else ""
            subtype = event.get("subtype", "")

            # Skip bot messages and message edits
            if subtype in ["bot_message", "message_changed", "message_deleted"]:
                return

            # Skip thread replies - only auto-reply to parent messages
            # (Use @mention for follow-up questions in threads - it has full context)
            if event.get("thread_ts") and event.get("thread_ts") != event.get("ts"):
                return

            text = event.get("text", "")
            ts = event.get("ts", "")
            user = event.get("user", "")

            # Get bot user ID if we don't have it
            if not self._bot_user_id:
                try:
                    auth_response = client.auth_test()
                    self._bot_user_id = auth_response.get("user_id")
                except Exception:
                    pass

            # Skip messages from the bot itself
            if user == self._bot_user_id:
                return

            # Skip if message mentions the bot (handled by app_mention)
            if self._bot_user_id and f"<@{self._bot_user_id}>" in text:
                return

            # Check if auto-reply is enabled globally
            if not SlackBot._auto_reply_enabled:
                return

            # Only auto-reply in designated channels
            if channel not in SlackBot.AUTO_REPLY_CHANNELS:
                return

            # Skip if we've already responded to this thread
            thread_key = f"{channel}:{ts}"
            if thread_key in self._responded_threads:
                return

            # Mark thread as responded
            self._responded_threads.add(thread_key)

            # Clean up old thread keys (keep last 1000)
            if len(self._responded_threads) > 1000:
                to_remove = list(self._responded_threads)[:500]
                for key in to_remove:
                    self._responded_threads.discard(key)

            print(f"[Clippy] Auto-reply in {channel}: {text[:100]}")

            # Acknowledge with context-aware message
            ack_msg = get_acknowledgment(text)
            say(ack_msg, thread_ts=ts)

            # Use Claude Tool Use (no thread context for initial auto-reply)
            result = invoke_claude_with_tools(text)
            response = result.get("response", "I'm not sure how to help with that.")
            response = redact_secrets(response)
            # Only add footer if not already present (avoid duplicates)
            if "Clippy is a work in progress" not in response:
                response += CLIPPY_FOOTER

            say(response, thread_ts=ts)

        self.handler = SocketModeHandler(self.app, self.app_token)

    def start(self, blocking: bool = False):
        """Start the Slack bot.

        Args:
            blocking: If True, blocks the current thread. If False, runs in background.
        """
        if not self.is_configured():
            print("[SlackBot] Slack tokens not configured, skipping bot startup")
            return

        try:
            from slack_bolt import App  # noqa: F401
        except ImportError:
            print("[SlackBot] slack-bolt not installed, skipping bot startup")
            return

        self._setup_app()

        if blocking:
            print("[SlackBot] Starting in foreground...")
            self.handler.start()
        else:
            print("[SlackBot] Starting in background thread...")
            self._thread = threading.Thread(target=self.handler.start, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop the Slack bot."""
        if self.handler:
            self.handler.close()
