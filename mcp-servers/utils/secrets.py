"""Secrets management for MCP server."""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")
SECRETS_NAME = os.environ.get("SECRETS_NAME", "mrrobot-ai-core/secrets")

# Cache for secrets
_secrets_cache = None


def get_secrets() -> dict:
    """Fetch secrets from AWS Secrets Manager with caching."""
    global _secrets_cache

    if _secrets_cache is not None:
        return _secrets_cache

    from botocore.config import Config

    try:
        config = Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 1})
        if AWS_PROFILE:
            session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
        else:
            session = boto3.Session(region_name=REGION)
        client = session.client("secretsmanager", config=config)
        response = client.get_secret_value(SecretId=SECRETS_NAME)
        _secrets_cache = json.loads(response["SecretString"])
        print(f"[Secrets] Loaded from {SECRETS_NAME}")
        return _secrets_cache
    except Exception as e:
        print(f"[Secrets] Warning: Could not fetch from Secrets Manager: {e}")
        return {}


def get_secret(key: str, default: str = "") -> str:
    """Get a specific secret value, checking env vars first."""
    # Check env var first
    env_value = os.environ.get(key, "")
    if env_value:
        return env_value

    # Fall back to Secrets Manager
    secrets = get_secrets()
    return secrets.get(key, default)

