"""Config loader for Clippy - loads service registry and prompts from S3.

Configs are cached with a TTL to avoid repeated S3 calls.
Falls back to defaults if S3 is unavailable.
"""

import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

# S3 bucket for configs - environment-aware
# Format: mrrobot-code-kb-{env}-{account_id}
_ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
_ACCOUNT_IDS = {
    "dev": "123456789012",
    "prod": "246295362269",
}
_account_id = _ACCOUNT_IDS.get(_ENVIRONMENT, "123456789012")
CONFIG_BUCKET = f"mrrobot-code-kb-{_ENVIRONMENT}-{_account_id}"
CONFIG_PREFIX = "clippy-config/"

# Cache settings
_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_s3_client():
    """Get S3 client."""
    return boto3.client("s3", region_name="us-east-1")


def _load_from_s3(key: str) -> str | None:
    """Load a file from S3, returns None if not found."""
    try:
        s3 = _get_s3_client()
        response = s3.get_object(Bucket=CONFIG_BUCKET, Key=f"{CONFIG_PREFIX}{key}")
        return response["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            print(f"[ConfigLoader] S3 key not found: {key}")
        else:
            print(f"[ConfigLoader] S3 error: {e}")
        return None
    except Exception as e:
        print(f"[ConfigLoader] Error loading {key}: {e}")
        return None


def _get_cached(key: str, loader_fn, default: Any = None) -> Any:
    """Get value from cache or load it."""
    now = time.time()

    if key in _cache:
        cached_value, cached_time = _cache[key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_value

    # Load fresh value
    value = loader_fn()
    if value is not None:
        _cache[key] = (value, now)
        return value

    # Return cached value even if expired (better than nothing)
    if key in _cache:
        return _cache[key][0]

    return default


def get_service_registry() -> dict:
    """Get service registry with aliases and metadata.

    Returns dict like:
    {
        "cast-core": {
            "full_name": "cast-core-service",
            "type": "backend",
            "lambda": "mrrobot-cast-core",
            "aliases": ["cast", "cast-core", "castcore"],
            "tech_stack": ["Node.js", "Lambda"],
            "description": "Core CAST processing service"
        },
        ...
    }
    """

    def loader():
        content = _load_from_s3("services.json")
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                print(f"[ConfigLoader] Invalid JSON in services.json: {e}")
        return None

    return _get_cached("services", loader, default=DEFAULT_SERVICE_REGISTRY)


def get_system_prompt() -> str:
    """Get Clippy system prompt from S3."""

    def loader():
        return _load_from_s3("system_prompt.txt")

    return _get_cached("system_prompt", loader, default=DEFAULT_SYSTEM_PROMPT)


def get_env_mappings() -> dict:
    """Get environment name mappings."""

    def loader():
        content = _load_from_s3("env_mappings.json")
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass
        return None

    return _get_cached("env_mappings", loader, default=DEFAULT_ENV_MAPPINGS)


def lookup_service(name: str) -> dict | None:
    """Look up a service by name or alias.

    Args:
        name: Service name, key, or alias (e.g., 'cast', 'cast-core', 'cast-core-service')

    Returns:
        Service info dict with full_name, type, aliases, tech_stack, description
        or None if not found
    """
    registry = get_service_registry()
    name_lower = name.lower().strip()

    # Direct key match
    if name_lower in registry:
        return {"key": name_lower, **registry[name_lower]}

    # Search by alias or full_name
    for key, info in registry.items():
        # Check full_name
        if info.get("full_name", "").lower() == name_lower:
            return {"key": key, **info}

        # Check aliases
        for alias in info.get("aliases", []):
            if alias.lower() == name_lower:
                return {"key": key, **info}

    return None


def clear_cache():
    """Clear all cached configs (useful for testing)."""
    global _cache
    _cache = {}
    print("[ConfigLoader] Cache cleared")


def reload_configs():
    """Force reload all configs from S3."""
    clear_cache()
    get_service_registry()
    get_system_prompt()
    get_env_mappings()
    print("[ConfigLoader] All configs reloaded")


# =============================================================================
# DEFAULT CONFIGS (fallback if S3 unavailable)
# =============================================================================

DEFAULT_ENV_MAPPINGS = {
    "prod": "production",
    "production": "production",
    "staging": "staging",
    "stage": "staging",
    "dev": "development",
    "development": "development",
    "sandbox": "sandbox",
    "devopslocal": "devopslocal",
}

# No hardcoded fallback - S3 is source of truth (129 services)
# If S3 fails, we return empty dict and tools will indicate "service not found"
DEFAULT_SERVICE_REGISTRY = {}

# Minimal fallback - S3 system_prompt.txt is the source of truth
# This only triggers if S3 is completely unavailable
DEFAULT_SYSTEM_PROMPT = """You are Clippy, a DevOps assistant in Slack.

⚠️ FALLBACK MODE: Could not load full prompt from S3. Running with minimal config.
Please alert DevOps if you see this message repeatedly.

Be concise and helpful. Use Slack formatting (*bold*, `code`).
Check logs and deploys when troubleshooting. Don't hallucinate data.
"""
