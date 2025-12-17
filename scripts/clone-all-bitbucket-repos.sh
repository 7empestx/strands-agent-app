#!/bin/bash
#
# Clone ALL repos from Bitbucket workspaces
# Uses CVE_BB_TOKEN env var for API access, SSH for cloning
#
# Usage: ./clone-all-bitbucket-repos.sh [OUTPUT_DIR]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${1:-$HOME/MrRobot/repos}"
BB_EMAIL="gstarkman@nex.io"

# Workspaces to scan (only mrrobot-labs)
WORKSPACES="mrrobot-labs"

# Check for token
if [ -z "$CVE_BB_TOKEN" ]; then
    echo "Error: CVE_BB_TOKEN environment variable not set"
    echo "Add to ~/.zshrc: export CVE_BB_TOKEN=\"your_token\""
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "=== Bitbucket Repository Cloner ==="
echo "Output directory: $OUTPUT_DIR"
echo "Workspaces: $WORKSPACES"
echo ""

# Track stats
TOTAL=0
CLONED=0
UPDATED=0
SKIPPED=0
ERRORS=0

for workspace in $WORKSPACES; do
    echo ""
    echo "=== Workspace: $workspace ==="

    PAGE=1
    while true; do
        # Fetch repo list from Bitbucket API
        response=$(curl -fsSL --request GET \
            --url "https://api.bitbucket.org/2.0/repositories/$workspace?page=$PAGE&pagelen=100" \
            --user "${BB_EMAIL}:${CVE_BB_TOKEN}" \
            --header 'Accept: application/json' 2>/dev/null) || {
            echo "  Error fetching page $PAGE for $workspace"
            break
        }

        if [ -z "$response" ]; then
            break
        fi

        # Get SSH clone URLs
        repos=$(echo "$response" | jq -r '.values[] | [.name, (.links.clone[] | select(.name == "ssh") | .href)] | @tsv' 2>/dev/null)

        if [ -z "$repos" ]; then
            break
        fi

        while IFS=$'\t' read -r repo_name ssh_url; do
            [ -z "$repo_name" ] && continue

            TOTAL=$((TOTAL + 1))
            repo_dir="$OUTPUT_DIR/$repo_name"

            if [ -d "$repo_dir/.git" ]; then
                # Repo exists, update it
                echo "  Updating: $repo_name"
                cd "$repo_dir"

                # Try to pull
                if git pull --ff-only 2>/dev/null; then
                    UPDATED=$((UPDATED + 1))
                    echo "    -> Updated"
                else
                    # Reset and pull
                    git fetch origin 2>/dev/null || true
                    default_branch=$(git remote show origin 2>/dev/null | grep 'HEAD branch' | cut -d: -f2 | tr -d ' ')
                    if [ -n "$default_branch" ]; then
                        git checkout "$default_branch" 2>/dev/null || true
                        git reset --hard "origin/$default_branch" 2>/dev/null || true
                        UPDATED=$((UPDATED + 1))
                        echo "    -> Reset to origin/$default_branch"
                    else
                        SKIPPED=$((SKIPPED + 1))
                        echo "    -> Skipped (couldn't update)"
                    fi
                fi

                cd - > /dev/null
            else
                # Clone new repo
                echo "  Cloning: $repo_name"
                if git clone --depth 1 "$ssh_url" "$repo_dir" 2>/dev/null; then
                    CLONED=$((CLONED + 1))
                    echo "    -> Cloned"
                else
                    ERRORS=$((ERRORS + 1))
                    echo "    -> Error cloning"
                fi
            fi
        done <<< "$repos"

        # Check for next page
        if ! echo "$response" | jq -e '.next' > /dev/null 2>&1; then
            break
        fi

        PAGE=$((PAGE + 1))
    done
done

# Summary
echo ""
echo "=== Summary ==="
echo "Total repos:    $TOTAL"
echo "New clones:     $CLONED"
echo "Updated:        $UPDATED"
echo "Skipped:        $SKIPPED"
echo "Errors:         $ERRORS"
echo ""
echo "Repos saved to: $OUTPUT_DIR"
