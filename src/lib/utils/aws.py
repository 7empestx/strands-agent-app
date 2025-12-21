"""Shared AWS client factories."""

import boto3
from botocore.config import Config

from .config import AWS_PROFILE, AWS_REGION


def get_session():
    """Get a boto3 session with proper configuration."""
    if AWS_PROFILE:
        return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return boto3.Session(region_name=AWS_REGION)


def get_bedrock_runtime():
    """Get Bedrock runtime client for model invocation."""
    config = Config(connect_timeout=30, read_timeout=60, retries={"max_attempts": 2})
    return get_session().client("bedrock-runtime", config=config)


def get_bedrock_agent_runtime():
    """Get Bedrock Agent Runtime client for Knowledge Base queries."""
    config = Config(connect_timeout=10, read_timeout=25, retries={"max_attempts": 1})
    return get_session().client("bedrock-agent-runtime", config=config)


def get_s3_client():
    """Get S3 client."""
    return get_session().client("s3")


def get_secrets_manager():
    """Get Secrets Manager client."""
    config = Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 1})
    return get_session().client("secretsmanager", config=config)


def get_logs_client():
    """Get CloudWatch Logs client."""
    return get_session().client("logs")


def get_cloudwatch_client():
    """Get CloudWatch client."""
    return get_session().client("cloudwatch")
