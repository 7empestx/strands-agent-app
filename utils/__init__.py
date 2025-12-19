"""Shared utilities for MrRobot AI Core."""

from .aws import (
    get_bedrock_agent,
    get_bedrock_agent_runtime,
    get_s3_client,
    get_secrets_manager,
    get_session,
)
from .config import (
    AWS_PROFILE,
    AWS_REGION,
    BITBUCKET_EMAIL,
    BITBUCKET_WORKSPACE,
    KNOWLEDGE_BASE_ID,
    S3_BUCKET,
    SECRETS_NAME,
)
from .secrets import get_secret, get_secrets

__all__ = [
    # AWS clients
    "get_session",
    "get_bedrock_agent_runtime",
    "get_bedrock_agent",
    "get_s3_client",
    "get_secrets_manager",
    # Config
    "AWS_REGION",
    "AWS_PROFILE",
    "KNOWLEDGE_BASE_ID",
    "S3_BUCKET",
    "BITBUCKET_WORKSPACE",
    "BITBUCKET_EMAIL",
    "SECRETS_NAME",
    # Secrets
    "get_secrets",
    "get_secret",
]

