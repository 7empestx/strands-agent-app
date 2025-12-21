"""Shared utilities for AWS, config, and secrets."""

from .aws import (
    get_bedrock_agent_runtime,
    get_bedrock_runtime,
    get_cloudwatch_client,
    get_logs_client,
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
    SECRETS_NAME,
)
from .secrets import get_secret

__all__ = [
    # AWS clients
    "get_session",
    "get_bedrock_runtime",
    "get_bedrock_agent_runtime",
    "get_s3_client",
    "get_secrets_manager",
    "get_logs_client",
    "get_cloudwatch_client",
    # Config
    "AWS_REGION",
    "AWS_PROFILE",
    "KNOWLEDGE_BASE_ID",
    "BITBUCKET_EMAIL",
    "BITBUCKET_WORKSPACE",
    "SECRETS_NAME",
    # Secrets
    "get_secret",
]
