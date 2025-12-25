"""AWS Bedrock client wrapper for Clippy.

Provides a singleton Bedrock runtime client for invoking Claude models.
"""

import boto3

# Bedrock client (reused across calls)
_bedrock_client = None


def get_bedrock_client():
    """Get or create Bedrock runtime client.

    Returns:
        boto3 bedrock-runtime client for us-east-1
    """
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")
    return _bedrock_client
