"""
Shared configuration for all agents and services.
Centralizes environment variable access and defaults.
"""

import os

# AWS Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")

# Bedrock Knowledge Base
KNOWLEDGE_BASE_ID = os.environ.get("CODE_KB_ID", "SAJJWYFTNG")
S3_BUCKET = os.environ.get("CODE_KB_BUCKET", "mrrobot-code-kb-dev-720154970215")

# Bitbucket
BITBUCKET_WORKSPACE = os.environ.get("BITBUCKET_WORKSPACE", "mrrobot-labs")
BITBUCKET_EMAIL = os.environ.get("BITBUCKET_EMAIL", "gstarkman@nex.io")

# Secrets
SECRETS_NAME = "mrrobot-ai-core/secrets"
