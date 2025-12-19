"""Secrets management for MrRobot AI Core.

Provides centralized access to secrets from AWS Secrets Manager.
Falls back to environment variables when Secrets Manager is unavailable.
"""

import json
import os

from .config import SECRETS_NAME

# Cache for secrets
_secrets_cache = None


def get_secrets() -> dict:
    """Fetch secrets from AWS Secrets Manager with caching.

    Returns:
        dict: All secrets from Secrets Manager, or empty dict on failure.
    """
    global _secrets_cache

    if _secrets_cache is not None:
        return _secrets_cache

    try:
        # Import here to avoid circular imports
        from .aws import get_secrets_manager

        client = get_secrets_manager()
        response = client.get_secret_value(SecretId=SECRETS_NAME)
        _secrets_cache = json.loads(response["SecretString"])
        print(f"[Secrets] Loaded from {SECRETS_NAME}")
        return _secrets_cache
    except Exception as e:
        print(f"[Secrets] Warning: Could not fetch from Secrets Manager: {e}")
        return {}


def get_secret(key: str, default: str = "") -> str:
    """Get a specific secret value, checking env vars first.

    Args:
        key: The secret key to retrieve.
        default: Default value if secret is not found.

    Returns:
        str: The secret value, or default if not found.
    """
    # Check env var first (allows local override)
    env_value = os.environ.get(key, "")
    if env_value:
        return env_value

    # Fall back to Secrets Manager
    secrets = get_secrets()
    return secrets.get(key, default)
