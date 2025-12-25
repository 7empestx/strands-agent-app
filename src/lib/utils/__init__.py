"""Shared utilities for AWS, config, secrets, and HTTP clients."""

from .aws import get_bedrock_agent_runtime, get_bedrock_runtime, get_s3_client, get_secrets_manager, get_session
from .config import AWS_PROFILE, AWS_REGION, BITBUCKET_EMAIL, BITBUCKET_WORKSPACE, KNOWLEDGE_BASE_ID, SECRETS_NAME
from .http_client import APIClient, make_request
from .secrets import get_secret

__all__ = [
    # AWS clients
    "get_session",
    "get_bedrock_runtime",
    "get_bedrock_agent_runtime",
    "get_s3_client",
    "get_secrets_manager",
    # Config
    "AWS_REGION",
    "AWS_PROFILE",
    "KNOWLEDGE_BASE_ID",
    "BITBUCKET_EMAIL",
    "BITBUCKET_WORKSPACE",
    "SECRETS_NAME",
    # Secrets
    "get_secret",
    # HTTP client
    "APIClient",
    "make_request",
]
