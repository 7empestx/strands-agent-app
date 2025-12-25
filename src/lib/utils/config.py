"""Shared configuration constants."""

import os

# AWS Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")

# Bedrock Knowledge Base
KNOWLEDGE_BASE_ID = os.environ.get("CODE_KB_ID", "SAJJWYFTNG")

# Bitbucket Configuration
# Email is required for new API tokens (not username like old App Passwords)
# See scripts/README-bitbucket-auth.md for details
BITBUCKET_EMAIL = os.environ.get("BITBUCKET_EMAIL", "gstarkman@nex.io")
BITBUCKET_WORKSPACE = "mrrobot-labs"

# Secrets Manager
SECRETS_NAME = "mrrobot-ai-core/secrets"
