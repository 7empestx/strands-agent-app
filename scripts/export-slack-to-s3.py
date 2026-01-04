#!/usr/bin/env python3
"""
Export Slack channel history to S3 for Knowledge Base ingestion.

Usage:
    python scripts/export-slack-to-s3.py --channels C0A3RJA9LSJ,C0A4ABCDEF
    python scripts/export-slack-to-s3.py --all-channels

Environment:
    SLACK_BOT_TOKEN - Bot token with channels:history, channels:read scopes
    AWS_PROFILE - AWS profile for S3 access
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import boto3
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configuration
S3_BUCKET = "mrrobot-code-kb-dev-123456789012"
S3_PREFIX = "slack-history"
REGION = "us-east-1"

# Channels to export by default (DevOps-related)
DEFAULT_CHANNELS = [
    "C0A3RJA9LSJ",  # devops-ai-test (or whatever this is)
]


def get_slack_client():
    """Get Slack client from Secrets Manager or environment."""
    token = os.environ.get("SLACK_BOT_TOKEN")

    if not token:
        # Try Secrets Manager
        try:
            secrets = boto3.client("secretsmanager", region_name=REGION)
            secret = secrets.get_secret_value(SecretId="mrrobot-ai-core/secrets")
            secret_dict = json.loads(secret["SecretString"])
            token = secret_dict.get("SLACK_BOT_TOKEN")
        except Exception as e:
            print(f"Could not get token from Secrets Manager: {e}")

    if not token:
        print("ERROR: SLACK_BOT_TOKEN not found in environment or Secrets Manager")
        sys.exit(1)

    return WebClient(token=token)


def get_s3_client():
    """Get S3 client."""
    return boto3.client("s3", region_name=REGION)


def get_channel_info(client, channel_id):
    """Get channel name and info."""
    try:
        result = client.conversations_info(channel=channel_id)
        return result["channel"]
    except SlackApiError as e:
        print(f"Error getting channel info for {channel_id}: {e}")
        return None


def get_user_name(client, user_id, user_cache):
    """Get user display name with caching."""
    if user_id in user_cache:
        return user_cache[user_id]

    try:
        result = client.users_info(user=user_id)
        name = result["user"].get("real_name") or result["user"].get("name", user_id)
        user_cache[user_id] = name
        return name
    except SlackApiError:
        user_cache[user_id] = user_id
        return user_id


def fetch_channel_history(client, channel_id, days_back=90):
    """Fetch all messages from a channel for the past N days."""
    messages = []
    user_cache = {}

    oldest = (datetime.now() - timedelta(days=days_back)).timestamp()

    try:
        cursor = None
        while True:
            result = client.conversations_history(channel=channel_id, oldest=str(oldest), limit=200, cursor=cursor)

            for msg in result.get("messages", []):
                # Skip bot messages and system messages
                if msg.get("subtype") in ["bot_message", "channel_join", "channel_leave"]:
                    continue

                user_id = msg.get("user", "unknown")
                user_name = get_user_name(client, user_id, user_cache)

                message_data = {
                    "timestamp": msg.get("ts"),
                    "datetime": datetime.fromtimestamp(float(msg.get("ts", 0))).isoformat(),
                    "user": user_name,
                    "user_id": user_id,
                    "text": msg.get("text", ""),
                    "thread_ts": msg.get("thread_ts"),
                    "reply_count": msg.get("reply_count", 0),
                }

                # Fetch thread replies if this is a parent message with replies
                if msg.get("reply_count", 0) > 0:
                    thread_messages = fetch_thread(client, channel_id, msg["ts"], user_cache)
                    message_data["thread"] = thread_messages

                messages.append(message_data)

            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

            print(f"  Fetched {len(messages)} messages so far...")

    except SlackApiError as e:
        print(f"Error fetching history: {e}")

    return messages


def fetch_thread(client, channel_id, thread_ts, user_cache):
    """Fetch all replies in a thread."""
    replies = []

    try:
        result = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=100)

        for msg in result.get("messages", [])[1:]:  # Skip parent message
            user_id = msg.get("user", "unknown")
            user_name = get_user_name(client, user_id, user_cache)

            replies.append(
                {
                    "timestamp": msg.get("ts"),
                    "datetime": datetime.fromtimestamp(float(msg.get("ts", 0))).isoformat(),
                    "user": user_name,
                    "text": msg.get("text", ""),
                }
            )

    except SlackApiError as e:
        print(f"Error fetching thread: {e}")

    return replies


def format_for_kb(channel_name, messages):
    """Format messages for Knowledge Base ingestion.

    Creates a document per conversation (message + thread).
    """
    documents = []

    for msg in messages:
        # Build conversation text
        lines = [
            f"# Slack Conversation in #{channel_name}",
            f"Date: {msg['datetime']}",
            f"",
            f"**{msg['user']}**: {msg['text']}",
        ]

        # Add thread replies
        if msg.get("thread"):
            lines.append("")
            lines.append("## Thread Replies:")
            for reply in msg["thread"]:
                lines.append(f"**{reply['user']}**: {reply['text']}")

        doc = {
            "content": "\n".join(lines),
            "metadata": {
                "source": "slack",
                "channel": channel_name,
                "timestamp": msg["timestamp"],
                "datetime": msg["datetime"],
                "user": msg["user"],
                "has_thread": bool(msg.get("thread")),
                "reply_count": msg.get("reply_count", 0),
            },
        }
        documents.append(doc)

    return documents


def upload_to_s3(s3_client, channel_name, documents):
    """Upload documents to S3."""
    uploaded = 0

    for doc in documents:
        # Create a unique key per conversation
        ts = doc["metadata"]["timestamp"].replace(".", "-")
        key = f"{S3_PREFIX}/{channel_name}/{ts}.txt"

        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=doc["content"].encode("utf-8"),
                ContentType="text/plain",
                Metadata={
                    "source": "slack",
                    "channel": channel_name,
                    "datetime": doc["metadata"]["datetime"],
                },
            )
            uploaded += 1
        except Exception as e:
            print(f"Error uploading {key}: {e}")

    return uploaded


def list_all_channels(client):
    """List all channels the bot has access to."""
    channels = []
    cursor = None

    try:
        while True:
            result = client.conversations_list(types="public_channel,private_channel", limit=200, cursor=cursor)

            for channel in result.get("channels", []):
                if channel.get("is_member"):
                    channels.append(
                        {
                            "id": channel["id"],
                            "name": channel["name"],
                        }
                    )

            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    except SlackApiError as e:
        print(f"Error listing channels: {e}")

    return channels


def main():
    parser = argparse.ArgumentParser(description="Export Slack history to S3")
    parser.add_argument("--channels", help="Comma-separated channel IDs")
    parser.add_argument("--all-channels", action="store_true", help="Export all channels bot is in")
    parser.add_argument("--days", type=int, default=90, help="Days of history to export (default: 90)")
    parser.add_argument("--list-channels", action="store_true", help="List available channels and exit")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't upload")

    args = parser.parse_args()

    print("=== Slack to S3 Export ===")
    print(f"Bucket: {S3_BUCKET}")
    print(f"Prefix: {S3_PREFIX}/")
    print(f"Days: {args.days}")
    print()

    slack_client = get_slack_client()
    s3_client = get_s3_client()

    # List channels mode
    if args.list_channels:
        print("Channels bot has access to:")
        for ch in list_all_channels(slack_client):
            print(f"  {ch['id']}: #{ch['name']}")
        return

    # Determine which channels to export
    if args.all_channels:
        channels = list_all_channels(slack_client)
        channel_ids = [ch["id"] for ch in channels]
    elif args.channels:
        channel_ids = [c.strip() for c in args.channels.split(",")]
    else:
        channel_ids = DEFAULT_CHANNELS

    print(f"Exporting {len(channel_ids)} channel(s)...")
    print()

    total_docs = 0

    for channel_id in channel_ids:
        print(f"Processing channel: {channel_id}")

        # Get channel info
        channel_info = get_channel_info(slack_client, channel_id)
        if not channel_info:
            print(f"  Skipping - could not get channel info")
            continue

        channel_name = channel_info.get("name", channel_id)
        print(f"  Channel name: #{channel_name}")

        # Fetch history
        print(f"  Fetching last {args.days} days of history...")
        messages = fetch_channel_history(slack_client, channel_id, args.days)
        print(f"  Found {len(messages)} messages")

        if not messages:
            continue

        # Format for KB
        documents = format_for_kb(channel_name, messages)
        print(f"  Created {len(documents)} documents")

        # Upload to S3
        if args.dry_run:
            print(f"  [DRY RUN] Would upload {len(documents)} documents")
        else:
            uploaded = upload_to_s3(s3_client, channel_name, documents)
            print(f"  Uploaded {uploaded} documents to S3")
            total_docs += uploaded

        print()

    print("=== Export Complete ===")
    print(f"Total documents uploaded: {total_docs}")
    print(f"S3 location: s3://{S3_BUCKET}/{S3_PREFIX}/")


if __name__ == "__main__":
    main()
