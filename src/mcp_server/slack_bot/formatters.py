"""Response formatting utilities for Clippy.

Handles Slack markdown conversion, secret redaction, and acknowledgment generation.
"""

import json
import re

from src.mcp_server.slack_bot.bedrock_client import get_bedrock_client


def convert_to_slack_markdown(text: str) -> str:
    """Convert standard markdown to Slack mrkdwn format.

    Slack uses different markdown:
    - *bold* instead of **bold**
    - _italic_ instead of *italic*
    - ~strikethrough~ (same)
    - `code` (same)
    - ```code block``` (same)
    """
    # Convert **bold** to *bold* (but not inside code blocks)
    # First, protect code blocks
    code_blocks = []

    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    # Save code blocks
    result = re.sub(r"```[\s\S]*?```", save_code_block, text)
    result = re.sub(r"`[^`]+`", save_code_block, result)

    # Convert **bold** to *bold*
    result = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", result)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        result = result.replace(f"__CODE_BLOCK_{i}__", block)

    return result


def redact_secrets(text: str) -> str:
    """Redact potential secrets from response text."""
    # Patterns that look like secrets
    patterns = [
        # PASSWORD='value' or PASSWORD="value" or PASSWORD=value
        (
            r"(PASSWORD|PASS|PWD|SECRET|TOKEN|KEY|CREDENTIAL|API_KEY|APIKEY|AUTH)\s*[=:]\s*['\"]?([^'\"\s,\n]{6,})['\"]?",
            r"\1=***REDACTED***",
        ),
        # Bearer tokens
        (r"(Bearer\s+)([A-Za-z0-9_\-\.]{20,})", r"\1***REDACTED***"),
        # AWS keys
        (r"(AKIA[A-Z0-9]{16})", r"***AWS_KEY_REDACTED***"),
        # Generic long alphanumeric strings that look like secrets (after = or :)
        (
            r"(['\"]?(?:password|secret|token|key|credential)['\"]?\s*[=:]\s*['\"]?)([A-Za-z0-9_\-\.]{12,})(['\"]?)",
            r"\1***REDACTED***\3",
        ),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def get_acknowledgment(message: str) -> str:
    """Generate a context-aware acknowledgment using Claude."""
    try:
        client = get_bedrock_client()

        prompt = f"""Generate a brief 2-5 word acknowledgment for this DevOps Slack message. Be casual and specific to what they're asking about. No emoji. No punctuation except "..." at the end.

Examples:
- "check this PR" → "Checking that PR..."
- "seeing 504 errors" → "Investigating those 504s..."
- "recent deploys for auth service" → "Checking auth deploys..."
- "help with SFTP access" → "Looking into SFTP..."

Message: "{message[:200]}"

Acknowledgment:"""

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = client.invoke_model(
            modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(body),
        )

        result = json.loads(response["body"].read())
        ack = result["content"][0]["text"].strip().strip('"')

        # Ensure it ends with ...
        if not ack.endswith("..."):
            ack = ack.rstrip(".") + "..."

        return ack

    except Exception as e:
        print(f"[Clippy] Ack generation failed: {e}")
        return "On it..."


def get_thread_context(client, channel: str, thread_ts: str, limit: int = 15) -> list:
    """Fetch previous messages from a Slack thread for context.

    Returns structured context that preserves:
    - Who said what (user vs bot)
    - Tool findings from bot responses
    - Enough history for follow-up questions
    """
    try:
        result = client.conversations_replies(
            channel=channel,
            ts=thread_ts,
            limit=limit,
        )
        messages = result.get("messages", [])

        # Get bot user ID to identify bot messages
        try:
            auth_response = client.auth_test()
            bot_user_id = auth_response.get("user_id")
        except Exception:
            bot_user_id = None

        # Format for context (skip the current message which is last)
        context = []
        for msg in messages[:-1]:  # Exclude current message
            user_id = msg.get("user", "")
            bot_id = msg.get("bot_id", "")
            text = msg.get("text", "")[:500]  # More context per message

            # Determine if this is from the bot
            is_bot = bool(bot_id) or (bot_user_id and user_id == bot_user_id)
            role = "Clippy" if is_bot else "User"

            context.append(f"{role}: {text}")

        return context
    except Exception as e:
        print(f"[SlackBot] Error fetching thread context: {e}")
        return []


def get_channel_info(client, channel_id: str) -> dict:
    """Get channel name and type from Slack.

    Returns:
        dict with 'name' and 'is_devops' keys
    """
    try:
        result = client.conversations_info(channel=channel_id)
        channel = result.get("channel", {})
        name = channel.get("name", "")

        # Check if this is a DevOps-related channel
        devops_keywords = ["devops", "infra", "platform", "sre", "ops", "deploy", "ci-cd"]
        is_devops = any(kw in name.lower() for kw in devops_keywords)

        return {
            "name": name,
            "is_devops": is_devops,
            "is_private": channel.get("is_private", False),
        }
    except Exception as e:
        print(f"[SlackBot] Error fetching channel info: {e}")
        return {"name": "", "is_devops": False, "is_private": False}


# Clippy UI constants
CLIPPY_INTRO = """Hi! I'm Clippy, your DevOps assistant.

I can help you:
- Search logs across all environments
- Investigate production issues
- Find code and configurations
- Check CloudWatch metrics and alarms

Just tell me what's going on!"""

CLIPPY_FOOTER = """
---
_Clippy is a work in progress! <https://ai-agent.mrrobot.dev/?page=feedback|Give feedback> to help improve._
_I only respond once per thread. Use `@Clippy-ai` to continue the conversation._"""
