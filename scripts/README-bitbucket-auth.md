# Bitbucket Authentication Guide

This guide covers Bitbucket API authentication for both local development (Claude Code) and production (MCP Server/Clippy).

## Token Types

Bitbucket supports two auth methods. **Workspace Access Tokens** are recommended for automated services.

| Token Type | Auth Method | Best For |
|------------|-------------|----------|
| **Workspace Access Token** | Bearer auth (`Authorization: Bearer TOKEN`) | Automated services (Clippy, MCP) |
| Personal API Token | Basic auth (`email:token`) | Local development, personal use |

## Creating a Workspace Access Token (Recommended for Clippy)

1. Go to **Bitbucket Workspace Settings** → **Access tokens**
   - URL: `https://bitbucket.org/mrrobot-labs/workspace/settings/access-tokens`
2. Click **Create access token**
3. Configure:
   - **Name:** `mrrobot-ai-core` or `clippy`
   - **Permissions:** Repositories: Read, Pull requests: Read
4. Copy the token (starts with `ATCTT3xFfGN0...`)

### Auth Method for Workspace Access Tokens

Workspace access tokens use **Bearer auth** (NOT Basic auth):

```bash
# Correct - Bearer auth
curl -H "Authorization: Bearer ATCTT3xFfGN0..." \
     "https://api.bitbucket.org/2.0/repositories/mrrobot-labs"

# WRONG - Basic auth does NOT work with workspace tokens
curl -u "email@example.com:ATCTT3xFfGN0..." ...
```

## Creating a Personal API Token (Alternative)

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token with scopes**
3. Select app: **Bitbucket**
4. Add scopes:
   - `read:repository:bitbucket`
   - `read:pullrequest:bitbucket`
   - `read:user:bitbucket`
5. Copy the token

### Auth Method for Personal Tokens

Personal API tokens use **Basic auth** with your Atlassian email:

```bash
# Basic auth with email
curl -u "gstarkman@nex.io:ATATT3xFfGF0..." \
     "https://api.bitbucket.org/2.0/repositories/mrrobot-labs"
```

## Updating Secrets Manager (for MCP/Clippy)

The MCP server reads auth config from AWS Secrets Manager. Set these values:

```bash
# Required
BITBUCKET_TOKEN=ATCTT3xFfGN0...  # The token

# For Workspace Access Tokens (Bearer auth)
BITBUCKET_AUTH_TYPE=bearer

# For Personal API Tokens (Basic auth) - also needs email
BITBUCKET_AUTH_TYPE=basic
BITBUCKET_EMAIL=gstarkman@nex.io
```

### Update via AWS Console

1. Go to AWS Secrets Manager → `mrrobot-ai-core/secrets`
2. Click **Retrieve secret value** → **Edit**
3. Update `BITBUCKET_TOKEN` and `BITBUCKET_AUTH_TYPE`
4. Redeploy ECS: `./scripts/deploy-to-ecs.sh`

### Update via CLI

```bash
# Get current secrets
AWS_PROFILE=dev aws secretsmanager get-secret-value \
  --secret-id mrrobot-ai-core/secrets \
  --query SecretString --output text | jq .

# Update (requires full JSON, be careful)
AWS_PROFILE=dev python3 -c "
import boto3
import json

client = boto3.Session(profile_name='dev').client('secretsmanager')
secret = json.loads(client.get_secret_value(SecretId='mrrobot-ai-core/secrets')['SecretString'])
secret['BITBUCKET_TOKEN'] = 'YOUR_NEW_TOKEN'
secret['BITBUCKET_AUTH_TYPE'] = 'bearer'  # or 'basic'
# secret['BITBUCKET_EMAIL'] = 'your@email.com'  # only if using basic auth

client.update_secret(SecretId='mrrobot-ai-core/secrets', SecretString=json.dumps(secret))
print('Updated!')
"
```

## Local Development

For local testing with Claude Code or `bitbucket-auth.sh`:

```bash
# Add to ~/.zshrc
export BITBUCKET_TOKEN="ATCTT3xFfGN0..."
export BITBUCKET_AUTH_TYPE="bearer"  # or "basic"
export BITBUCKET_EMAIL="gstarkman@nex.io"  # only needed for basic auth

# Reload
source ~/.zshrc

# Test
source scripts/bitbucket-auth.sh
bb_test
```

## How bitbucket.py Handles Auth

The code (`src/lib/bitbucket.py`) reads auth type from Secrets Manager:

```python
def _get_auth_kwargs(token: str) -> dict:
    auth_type = get_secret("BITBUCKET_AUTH_TYPE") or "basic"
    if auth_type == "bearer":
        return {"headers": {"Authorization": f"Bearer {token}"}}
    else:
        return {"auth": (get_secret("BITBUCKET_EMAIL"), token)}
```

## Troubleshooting

### 401 Unauthorized

1. **Check token is correct:** Copy-paste fresh from Bitbucket
2. **Check auth type matches token type:**
   - Workspace Access Token → must use `bearer`
   - Personal API Token → must use `basic` with email
3. **Check Secrets Manager has the right values**

### 403 Forbidden

The mrrobot-labs workspace may require VPN access. Ensure the server is on VPN.

### Token Expired

Workspace access tokens can be set to never expire. Personal tokens last 1 year max.
Create a new token and update Secrets Manager.

## App Passwords Deprecated

App Passwords were deprecated September 2025 and will stop working June 2026.
If you have old code using app passwords, migrate to API tokens.

## Shell Helper Functions

Source `scripts/bitbucket-auth.sh` for convenient CLI access:

```bash
source scripts/bitbucket-auth.sh

bb_test              # Test auth is working
bb_get "/user"       # Raw API GET
bb_pr cast-core 123  # Get PR details
bb_prs cast-core     # List open PRs
bb_my_prs            # Your open PRs
```
