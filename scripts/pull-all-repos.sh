#!/bin/bash
#
# Pull latest from main/master for all repos using SSH
# Usage: ./pull-all-repos.sh [REPOS_DIR]
#

set -e

REPOS_DIR="${1:-$HOME/MrRobot/repos}"

echo "=== Pull All Repos (SSH) ==="
echo "Directory: $REPOS_DIR"
echo ""

# Track stats
TOTAL=0
UPDATED=0
SKIPPED=0
ERRORS=0

for repo in "$REPOS_DIR"/*; do
    if [ -d "$repo/.git" ]; then
        repo_name=$(basename "$repo")
        TOTAL=$((TOTAL + 1))

        cd "$repo" || continue

        # Get current remote URL
        current_url=$(git remote get-url origin 2>/dev/null || echo "")

        if [ -z "$current_url" ]; then
            echo "[$repo_name] No origin remote, skipping"
            SKIPPED=$((SKIPPED + 1))
            cd - > /dev/null
            continue
        fi

        # Convert HTTPS to SSH if needed
        if [[ "$current_url" == https://bitbucket.org/* ]]; then
            # Extract workspace/repo from HTTPS URL
            path_part=$(echo "$current_url" | sed 's|https://bitbucket.org/||' | sed 's|\.git$||')
            ssh_url="git@bitbucket.org:${path_part}.git"

            echo "[$repo_name] Converting to SSH..."
            git remote set-url origin "$ssh_url"
        fi

        # Find default branch (main or master)
        default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "")

        if [ -z "$default_branch" ]; then
            # Try to detect from remote
            if git show-ref --verify --quiet refs/remotes/origin/main 2>/dev/null; then
                default_branch="main"
            elif git show-ref --verify --quiet refs/remotes/origin/master 2>/dev/null; then
                default_branch="master"
            else
                default_branch="main"  # Default guess
            fi
        fi

        # Checkout default branch and pull
        current_branch=$(git branch --show-current 2>/dev/null || echo "")

        echo "[$repo_name] Pulling $default_branch..."

        if git fetch origin "$default_branch" 2>/dev/null; then
            # Check if we need to switch branches
            if [ "$current_branch" != "$default_branch" ]; then
                # Stash any local changes
                git stash -q 2>/dev/null || true
                git checkout "$default_branch" 2>/dev/null || git checkout -b "$default_branch" "origin/$default_branch" 2>/dev/null || true
            fi

            if git pull origin "$default_branch" 2>/dev/null; then
                UPDATED=$((UPDATED + 1))
                echo "  -> Updated"
            else
                ERRORS=$((ERRORS + 1))
                echo "  -> Pull failed (conflicts?)"
            fi
        else
            ERRORS=$((ERRORS + 1))
            echo "  -> Fetch failed"
        fi

        cd - > /dev/null || exit 1
    fi
done

echo ""
echo "=== Summary ==="
echo "Total repos:  $TOTAL"
echo "Updated:      $UPDATED"
echo "Skipped:      $SKIPPED"
echo "Errors:       $ERRORS"
