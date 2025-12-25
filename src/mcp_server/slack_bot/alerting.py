"""Error alerting for Clippy Slack bot.

Posts error alerts to the #clippy-ai-dev channel for monitoring.
"""

# Channel for Clippy error alerts
CLIPPY_DEV_CHANNEL = "C0A3RJA9LSJ"  # #clippy-ai-dev

# Global Slack client - set when SlackBot initializes
_slack_client = None


def set_slack_client(client):
    """Set the Slack client for alerting.

    Called by SlackBot during initialization.
    """
    global _slack_client
    _slack_client = client


def get_slack_client():
    """Get the current Slack client."""
    return _slack_client


def alert_error(error_type: str, message: str, details: dict = None):
    """Post an error alert to #clippy-ai-dev channel.

    Args:
        error_type: Short error type (e.g., "Tool Failure", "API Error")
        message: Human-readable error message
        details: Optional dict with additional context
    """
    if not _slack_client:
        print(f"[Clippy Alert] {error_type}: {message} (no Slack client)")
        return

    try:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Clippy Error: {error_type}*\n{message}",
                },
            }
        ]

        if details:
            detail_text = "\n".join([f"• *{k}*: `{v}`" for k, v in details.items()])
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": detail_text}})

        _slack_client.chat_postMessage(
            channel=CLIPPY_DEV_CHANNEL,
            text=f"⚠️ Clippy Error: {error_type} - {message}",
            blocks=blocks,
        )
    except Exception as e:
        print(f"[Clippy Alert] Failed to send alert: {e}")
