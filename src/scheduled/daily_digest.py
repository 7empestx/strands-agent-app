#!/usr/bin/env python3
"""Daily DevOps Digest - Posts a summary to Slack each morning.

Runs as a scheduled ECS task via EventBridge.
Gathers health info from key services and posts to #devops channel.
"""

import json
import os
import sys
from datetime import datetime, timedelta

# Force unbuffered output for CloudWatch Logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import boto3

# Add app directory to path for imports (works in Docker where WORKDIR=/app)
app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, app_dir)

from src.lib.bitbucket import get_pipeline_status
from src.lib.coralogix import handle_get_recent_errors

# Configuration
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#devops")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

# Key services to monitor
KEY_SERVICES = [
    "mrrobot-cast-core",
    "mrrobot-auth-rest",
    "mrrobot-payments-rest",
    "mrrobot-messaging-rest",
    "mrrobot-merchant-rest",
]


# Cache for Slack token (fetched at startup to avoid clock skew issues)
_slack_token_cache = None


def get_slack_token():
    """Get Slack token from secrets (cached)."""
    global _slack_token_cache
    if _slack_token_cache is not None:
        return _slack_token_cache

    try:
        secrets = boto3.client("secretsmanager", region_name="us-east-1")
        secret = secrets.get_secret_value(SecretId="mrrobot-ai-core/secrets")
        secret_dict = json.loads(secret["SecretString"])
        _slack_token_cache = secret_dict.get("SLACK_BOT_TOKEN")
        print("[Digest] Slack token retrieved successfully")
        return _slack_token_cache
    except Exception as e:
        print(f"[Digest] Could not get Slack token: {e}")
        return None


def post_to_slack(message: str, blocks: list = None):
    """Post message to Slack channel."""
    slack_token = get_slack_token()

    if not slack_token:
        print("[Digest] No Slack token available")
        return False

    try:
        from slack_sdk import WebClient

        client = WebClient(token=slack_token)

        result = client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text=message,
            blocks=blocks,
            unfurl_links=False,
        )
        print(f"[Digest] Posted to Slack: {result['ts']}")
        return True
    except Exception as e:
        print(f"[Digest] Error posting to Slack: {e}")
        return False


def get_error_summary() -> dict:
    """Get error summary for key services in the last 24 hours."""
    errors_by_service = {}

    for service in KEY_SERVICES:
        try:
            result = handle_get_recent_errors(
                service_name=service,
                environment="prod",
                hours_back=24,
                limit=100,
            )
            error_count = result.get("total_errors", 0)
            if error_count > 0:
                errors_by_service[service] = {
                    "count": error_count,
                    "top_errors": result.get("errors", [])[:3],
                }
        except Exception as e:
            print(f"[Digest] Error getting errors for {service}: {e}")

    return errors_by_service


def get_deployment_summary() -> list:
    """Get recent deployments in the last 24 hours."""
    deployments = []

    for service in KEY_SERVICES:
        try:
            # Extract repo name from service name
            if "cast-core" in service:
                repo_name = "cast-core-service"
            elif "auth-rest" in service:
                repo_name = "mrrobot-auth-rest"
            elif "payments-rest" in service:
                repo_name = "mrrobot-payment-service"  # Note: singular 'payment'
            elif "messaging-rest" in service:
                repo_name = "mrrobot-messaging-rest"
            elif "merchant-rest" in service:
                repo_name = "merchant-service"  # Note: no 'mrrobot-' prefix
            else:
                repo_name = service.replace("mrrobot-", "") + "-service"

            result = get_pipeline_status(repo_name, limit=5)

            # Filter to last 24 hours and successful deployments
            cutoff = datetime.utcnow() - timedelta(hours=24)
            for pipeline in result.get("pipelines", []):
                created = pipeline.get("created_on", "")
                if created:
                    try:
                        pipeline_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if pipeline_time.replace(tzinfo=None) > cutoff:
                            if pipeline.get("state", {}).get("result", {}).get("name") == "SUCCESSFUL":
                                deployments.append(
                                    {
                                        "service": service,
                                        "commit": pipeline.get("target", {}).get("commit", {}).get("message", "")[:50],
                                        "author": pipeline.get("creator", {}).get("display_name", "Unknown"),
                                        "time": created,
                                    }
                                )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Digest] Error getting deployments for {service}: {e}")

    return deployments[:10]  # Limit to 10 most recent


def format_digest() -> tuple[str, list]:
    """Format the daily digest as Slack blocks."""
    now = datetime.utcnow()
    date_str = now.strftime("%A, %B %d, %Y")

    # Gather data
    print("[Digest] Gathering error summary...")
    errors = get_error_summary()

    print("[Digest] Gathering deployment summary...")
    deployments = get_deployment_summary()

    # Build Slack blocks
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Daily DevOps Digest - {date_str}", "emoji": True}},
        {"type": "divider"},
    ]

    # Error Summary
    if errors:
        error_lines = []
        total_errors = sum(e["count"] for e in errors.values())
        for service, data in sorted(errors.items(), key=lambda x: -x[1]["count"]):
            error_lines.append(f"• *{service}*: {data['count']} errors")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Errors (last 24h)*: {total_errors} total\n" + "\n".join(error_lines[:5]),
                },
            }
        )
    else:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Errors*: No errors in key services (last 24h)"}}
        )

    # Deployment Summary
    if deployments:
        deploy_lines = []
        for d in deployments[:5]:
            service_short = d["service"].replace("mrrobot-", "")
            deploy_lines.append(f"• *{service_short}*: {d['commit'][:40]}... ({d['author']})")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Deployments (last 24h)*: {len(deployments)}\n" + "\n".join(deploy_lines),
                },
            }
        )
    else:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Deployments*: No deployments in last 24h"}}
        )

    # Footer
    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_Generated by Clippy at {now.strftime('%H:%M UTC')} • Reply to this thread for questions_",
                }
            ],
        }
    )

    # Plain text fallback
    text = f"Daily DevOps Digest - {date_str}"

    return text, blocks


def main():
    """Main entry point for daily digest."""
    print(f"[Digest] Starting daily digest at {datetime.utcnow().isoformat()}")
    print(f"[Digest] Environment: {ENVIRONMENT}")
    print(f"[Digest] Channel: {SLACK_CHANNEL}")

    # Fetch Slack token early to avoid clock skew issues after slow API calls
    print("[Digest] Pre-fetching Slack token...")
    if not get_slack_token():
        print("[Digest] WARNING: Could not get Slack token, will try again later")

    try:
        text, blocks = format_digest()
        success = post_to_slack(text, blocks)

        if success:
            print("[Digest] Daily digest posted successfully")
            return 0
        else:
            print("[Digest] Failed to post digest")
            return 1
    except Exception as e:
        print(f"[Digest] Error generating digest: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
