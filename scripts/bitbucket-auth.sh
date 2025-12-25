#!/bin/bash
# Bitbucket API Authentication Helper
# Usage: source scripts/bitbucket-auth.sh && bb_get "/user"

# Config
BB_EMAIL="gstarkman@nex.io"
BB_API="https://api.bitbucket.org/2.0"

# Get token: env var > extract from zshrc
if [ -n "$BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED" ]; then
    BB_TOKEN="$BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED"
else
    BB_TOKEN=$(grep 'BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED=' ~/.zshrc 2>/dev/null | cut -d'"' -f2)
fi

# Validate
if [ -z "$BB_TOKEN" ]; then
    echo "ERROR: BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED not set"
    echo "Add to ~/.zshrc:"
    echo '  export BITBUCKET_ATLASSIAN_API_TOKEN_SCOPED="your-token"'
    return 1 2>/dev/null || exit 1
fi

# Test auth
bb_test() {
    echo "Testing Bitbucket auth..."
    echo "Email: $BB_EMAIL"
    echo "Token: ${BB_TOKEN:0:20}..."
    echo ""

    RESPONSE=$(curl -s -w "\n%{http_code}" -u "$BB_EMAIL:$BB_TOKEN" "$BB_API/user")
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [ "$HTTP_CODE" = "200" ]; then
        NAME=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('display_name','unknown'))" 2>/dev/null)
        echo "SUCCESS: Authenticated as $NAME"
        return 0
    else
        echo "FAILED: HTTP $HTTP_CODE"
        echo "$BODY"
        return 1
    fi
}

# Generic GET request
bb_get() {
    local endpoint="$1"
    curl -s -u "$BB_EMAIL:$BB_TOKEN" "$BB_API$endpoint"
}

# Get PR details (tries both workspaces)
bb_pr() {
    local repo="$1"
    local pr_id="$2"
    local workspace="${3:-}"

    if [ -z "$repo" ] || [ -z "$pr_id" ]; then
        echo "Usage: bb_pr <repo> <pr_id> [workspace]"
        echo "Example: bb_pr mrrobot-iam-terraform 138"
        echo "         bb_pr cforce-service 1232 emvio"
        return 1
    fi

    # Try specified workspace, or both if not specified
    local result=""
    if [ -n "$workspace" ]; then
        result=$(bb_get "/repositories/$workspace/$repo/pullrequests/$pr_id")
    else
        # Try mrrobot-labs first, then emvio
        result=$(bb_get "/repositories/mrrobot-labs/$repo/pullrequests/$pr_id")
        if echo "$result" | grep -q '"error"'; then
            result=$(bb_get "/repositories/emvio/$repo/pullrequests/$pr_id")
        fi
    fi

    echo "$result" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if 'error' in d:
        print(f'Error: {d[\"error\"][\"message\"]}')
    else:
        print(f'Title: {d[\"title\"]}')
        print(f'State: {d[\"state\"]}')
        print(f'Author: {d[\"author\"][\"display_name\"]}')
        print(f'Source: {d[\"source\"][\"branch\"][\"name\"]} -> {d[\"destination\"][\"branch\"][\"name\"]}')
        print(f'Created: {d[\"created_on\"][:10]}')
        print(f'Updated: {d[\"updated_on\"][:10]}')
        print(f'Link: https://bitbucket.org/emvio/{sys.argv[1] if len(sys.argv) > 1 else \"repo\"}/pull-requests/{sys.argv[2] if len(sys.argv) > 2 else \"?\"}/diff')
        desc = d.get('description') or 'None'
        print(f'Description: {desc[:300]}')
except Exception as e:
    print(f'Parse error: {e}')
" "$repo" "$pr_id"
}

# List open PRs for a repo
bb_prs() {
    local repo="$1"

    if [ -z "$repo" ]; then
        echo "Usage: bb_prs <repo>"
        echo "Example: bb_prs mrrobot-iam-terraform"
        return 1
    fi

    bb_get "/repositories/emvio/$repo/pullrequests?state=OPEN" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    prs = d.get('values', [])
    print(f'Open PRs in $1: {len(prs)}')
    for pr in prs:
        print(f'  #{pr[\"id\"]}: {pr[\"title\"][:60]} ({pr[\"author\"][\"display_name\"]})')
except Exception as e:
    print(f'Parse error: {e}')
" "$repo"
}

# List my open PRs across all repos
bb_my_prs() {
    echo "Finding your open PRs..."
    bb_get "/pullrequests/gstarkman?state=OPEN" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    prs = d.get('values', [])
    print(f'Your open PRs: {len(prs)}')
    for pr in prs:
        repo = pr['destination']['repository']['name']
        print(f'  #{pr[\"id\"]} {repo}: {pr[\"title\"][:50]}')
except Exception as e:
    print(f'Parse error: {e}')
"
}

# Update secrets in AWS
bb_update_secrets() {
    echo "Updating Bitbucket token in AWS Secrets Manager..."

    if [ -z "$BB_TOKEN" ]; then
        echo "ERROR: No token to update"
        return 1
    fi

    # Get current secrets
    CURRENT=$(AWS_PROFILE=dev aws secretsmanager get-secret-value --secret-id "mrrobot-ai-core/secrets" --query 'SecretString' --output text)

    # Update BITBUCKET_TOKEN
    UPDATED=$(echo "$CURRENT" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
d['BITBUCKET_TOKEN'] = '$BB_TOKEN'
d['BITBUCKET_EMAIL'] = '$BB_EMAIL'
print(json.dumps(d))
")

    # Push to secrets manager
    AWS_PROFILE=dev aws secretsmanager put-secret-value \
        --secret-id "mrrobot-ai-core/secrets" \
        --secret-string "$UPDATED"

    echo "Done. Restart MCP server to pick up new token."
}

echo "Bitbucket auth loaded. Commands:"
echo "  bb_test        - Test authentication"
echo "  bb_pr <repo> <id> - Get PR details"
echo "  bb_prs <repo>  - List open PRs in repo"
echo "  bb_my_prs      - List your open PRs"
echo "  bb_get <path>  - Raw API GET"
echo "  bb_update_secrets - Update AWS secrets"
