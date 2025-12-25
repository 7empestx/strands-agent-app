"""Feedback collection for Clippy responses.

Tracks user reactions (thumbs up/down) to learn what responses work well.
Stores feedback in S3 for later analysis.
"""

import json
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

# S3 bucket for feedback storage
FEEDBACK_BUCKET = "mrrobot-code-kb-dev-720154970215"
FEEDBACK_PREFIX = "clippy-feedback/"

# In-memory cache of recent messages for feedback correlation
# Maps message_ts -> message metadata
_recent_messages = {}
MAX_CACHED_MESSAGES = 500


def _get_s3_client():
    """Get S3 client."""
    return boto3.client("s3", region_name="us-east-1")


def store_message_for_feedback(
    message_ts: str,
    channel: str,
    user_query: str,
    tools_used: list,
    response_preview: str,
    duration_ms: float = 0,
):
    """Store message metadata for later feedback correlation.

    Called after Clippy sends a response so we can correlate reactions.

    Args:
        message_ts: Slack message timestamp (unique ID)
        channel: Channel ID where message was sent
        user_query: Original user question
        tools_used: List of tools that were called
        response_preview: First 500 chars of response
        duration_ms: How long the response took
    """
    global _recent_messages

    _recent_messages[message_ts] = {
        "channel": channel,
        "user_query": user_query[:500],
        "tools_used": tools_used,
        "response_preview": response_preview[:500],
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Clean up old entries
    if len(_recent_messages) > MAX_CACHED_MESSAGES:
        # Remove oldest half
        sorted_keys = sorted(_recent_messages.keys())
        for key in sorted_keys[: MAX_CACHED_MESSAGES // 2]:
            del _recent_messages[key]

    print(f"[Feedback] Stored message {message_ts} for feedback tracking")


def record_feedback(
    message_ts: str,
    reaction: str,
    user_id: str,
    channel: str = None,
) -> bool:
    """Record user feedback (reaction) on a Clippy response.

    Args:
        message_ts: Slack message timestamp that received the reaction
        reaction: Reaction name (e.g., 'thumbsup', 'thumbsdown', '+1', '-1')
        user_id: User who added the reaction
        channel: Channel where reaction was added

    Returns:
        True if feedback was recorded, False if message not found
    """
    # Normalize reaction names
    positive_reactions = {"thumbsup", "+1", "white_check_mark", "heavy_check_mark", "ok_hand", "tada"}
    negative_reactions = {"thumbsdown", "-1", "x", "no_entry", "warning"}

    if reaction in positive_reactions:
        sentiment = "positive"
    elif reaction in negative_reactions:
        sentiment = "negative"
    else:
        # Unknown reaction, don't track
        return False

    # Get message metadata from cache
    message_data = _recent_messages.get(message_ts, {})

    feedback_entry = {
        "message_ts": message_ts,
        "channel": channel or message_data.get("channel", "unknown"),
        "reaction": reaction,
        "sentiment": sentiment,
        "user_id": user_id,
        "feedback_time": datetime.utcnow().isoformat(),
        # Include original message data if available
        "user_query": message_data.get("user_query", ""),
        "tools_used": message_data.get("tools_used", []),
        "response_preview": message_data.get("response_preview", ""),
        "response_duration_ms": message_data.get("duration_ms", 0),
        "original_timestamp": message_data.get("timestamp", ""),
    }

    # Store to S3
    try:
        s3 = _get_s3_client()
        date_str = datetime.utcnow().strftime("%Y/%m/%d")
        key = f"{FEEDBACK_PREFIX}{date_str}/{message_ts}_{sentiment}.json"

        s3.put_object(
            Bucket=FEEDBACK_BUCKET,
            Key=key,
            Body=json.dumps(feedback_entry, indent=2),
            ContentType="application/json",
        )

        print(f"[Feedback] Recorded {sentiment} feedback for message {message_ts}")
        return True

    except ClientError as e:
        print(f"[Feedback] S3 error storing feedback: {e}")
        return False
    except Exception as e:
        print(f"[Feedback] Error storing feedback: {e}")
        return False


def get_feedback_summary(days: int = 7) -> dict:
    """Get summary of feedback over the past N days.

    Args:
        days: Number of days to look back

    Returns:
        dict with positive/negative counts, common tools in good/bad responses
    """
    try:
        s3 = _get_s3_client()

        positive_count = 0
        negative_count = 0
        positive_tools = {}
        negative_tools = {}

        # List objects for past N days
        from datetime import timedelta

        for i in range(days):
            date = datetime.utcnow() - timedelta(days=i)
            date_str = date.strftime("%Y/%m/%d")
            prefix = f"{FEEDBACK_PREFIX}{date_str}/"

            try:
                response = s3.list_objects_v2(Bucket=FEEDBACK_BUCKET, Prefix=prefix)
                for obj in response.get("Contents", []):
                    # Read feedback entry
                    content = s3.get_object(Bucket=FEEDBACK_BUCKET, Key=obj["Key"])
                    entry = json.loads(content["Body"].read())

                    sentiment = entry.get("sentiment", "")
                    tools = entry.get("tools_used", [])

                    if sentiment == "positive":
                        positive_count += 1
                        for tool in tools:
                            positive_tools[tool] = positive_tools.get(tool, 0) + 1
                    elif sentiment == "negative":
                        negative_count += 1
                        for tool in tools:
                            negative_tools[tool] = negative_tools.get(tool, 0) + 1

            except ClientError:
                continue

        total = positive_count + negative_count
        return {
            "period_days": days,
            "total_feedback": total,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "satisfaction_rate": (positive_count / total * 100) if total > 0 else 0,
            "positive_tools": dict(sorted(positive_tools.items(), key=lambda x: -x[1])[:10]),
            "negative_tools": dict(sorted(negative_tools.items(), key=lambda x: -x[1])[:10]),
        }

    except Exception as e:
        print(f"[Feedback] Error getting summary: {e}")
        return {"error": str(e)}
