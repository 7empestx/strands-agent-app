#!/bin/bash
#
# Update npm audit data for all Bitbucket repos
# Usage: ./update-audits.sh [REPOS_BASE_DIR]
#
# Requires: BITBUCKET_USERNAME and API_KEY environment variables
# or repos already cloned locally
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../data/npm-audits"
REPOS_BASE_DIR="${1:-$HOME/repos}"

# Bitbucket workspaces to scan (same as clone-all-bitbucket-repos.sh)
WORKSPACES="mrrobot-labs mrrobot-archive mrrobot-devops mrrobot-crypto emvio emviomobile cms-data cmsphilippines"

mkdir -p "$OUTPUT_DIR"

echo "=== npm Audit Scanner ==="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Track stats
TOTAL=0
SCANNED=0
SKIPPED=0
ERRORS=0

# Scan a single package.json location
scan_package() {
    local pkg_dir="$1"
    local output_name="$2"

    cd "$pkg_dir" || return 1

    # Generate package-lock.json if it doesn't exist
    if [ ! -f "package-lock.json" ]; then
        echo "  -> Generating package-lock.json..."
        npm install --package-lock-only --ignore-scripts 2>/dev/null || true
    fi

    # Run npm audit (returns non-zero when vulns found, so use || true)
    npm audit --json > "$OUTPUT_DIR/${output_name}.json" 2>/dev/null || true

    # Check if we got valid JSON output
    if [ -s "$OUTPUT_DIR/${output_name}.json" ] && jq -e . "$OUTPUT_DIR/${output_name}.json" > /dev/null 2>&1; then
        SCANNED=$((SCANNED + 1))

        # Quick summary
        if command -v jq &> /dev/null; then
            vulns=$(jq -r '.metadata.vulnerabilities.total // 0' "$OUTPUT_DIR/${output_name}.json" 2>/dev/null || echo "?")
            echo "  -> Found $vulns vulnerabilities"
        fi
        cd - > /dev/null || exit 1
        return 0
    else
        ERRORS=$((ERRORS + 1))
        echo "  -> Error running npm audit"
        rm -f "$OUTPUT_DIR/${output_name}.json"
        cd - > /dev/null || exit 1
        return 1
    fi
}

# Option 1: Scan already-cloned repos from a directory
scan_local_repos() {
    local base_dir="$1"

    echo "Scanning local repos in: $base_dir"
    echo ""

    for repo in "$base_dir"/*; do
        if [ -d "$repo" ]; then
            repo_name=$(basename "$repo")
            TOTAL=$((TOTAL + 1))

            if [ -f "$repo/package.json" ]; then
                echo "Scanning: $repo_name"
                scan_package "$repo" "$repo_name"
            else
                SKIPPED=$((SKIPPED + 1))
                echo "Skipping: $repo_name (no package.json)"
            fi
        fi
    done
}

# Option 2: Scan repos directly from Bitbucket (requires API credentials)
scan_bitbucket_repos() {
    if [ -z "$BITBUCKET_USERNAME" ] || [ -z "$API_KEY" ]; then
        echo "Error: BITBUCKET_USERNAME and API_KEY required for Bitbucket scanning"
        exit 1
    fi

    local temp_dir
    temp_dir=$(mktemp -d)

    echo "Scanning Bitbucket repos (temp dir: $temp_dir)"
    echo ""

    for workspace in $WORKSPACES; do
        echo "=== Workspace: $workspace ==="

        PAGE=1
        while true; do
            # Fetch repo list from Bitbucket API
            response=$(curl -fsSL --request GET \
                --url "https://api.bitbucket.org/2.0/repositories/$workspace?page=$PAGE" \
                --header "Authorization: Basic $(echo -n "$BITBUCKET_USERNAME:$API_KEY" | base64)" \
                --header 'Accept: application/json' 2>/dev/null)

            if [ -z "$response" ]; then
                break
            fi

            # Get repo clone URLs
            repos=$(echo "$response" | jq -r '.values[].links.clone[] | select(.name == "ssh") | .href' 2>/dev/null)

            for repo_url in $repos; do
                repo_name=$(basename "$repo_url" .git)
                TOTAL=$((TOTAL + 1))

                echo "Processing: $repo_name"

                # Shallow clone just to check package.json
                if git clone --depth 1 -q "$repo_url" "$temp_dir/$repo_name" 2>/dev/null; then
                    if [ -f "$temp_dir/$repo_name/package.json" ]; then
                        cd "$temp_dir/$repo_name" || continue

                        # Install deps and audit
                        npm install --package-lock-only --ignore-scripts 2>/dev/null

                        if npm audit --json > "$OUTPUT_DIR/${repo_name}.json" 2>/dev/null; then
                            SCANNED=$((SCANNED + 1))
                            echo "  -> Scanned"
                        else
                            ERRORS=$((ERRORS + 1))
                            rm -f "$OUTPUT_DIR/${repo_name}.json"
                        fi

                        cd - > /dev/null || exit 1
                    else
                        SKIPPED=$((SKIPPED + 1))
                    fi

                    rm -rf "${temp_dir:?}/$repo_name"
                else
                    ERRORS=$((ERRORS + 1))
                    echo "  -> Clone failed"
                fi
            done

            # Check for next page
            if ! echo "$response" | jq -e '.next' > /dev/null 2>&1; then
                break
            fi

            PAGE=$((PAGE + 1))
        done
    done

    rm -rf "$temp_dir"
}

# Main
if [ -d "$REPOS_BASE_DIR" ]; then
    scan_local_repos "$REPOS_BASE_DIR"
elif [ -n "$BITBUCKET_USERNAME" ] && [ -n "$API_KEY" ]; then
    scan_bitbucket_repos
else
    echo "Usage: $0 [REPOS_BASE_DIR]"
    echo ""
    echo "Options:"
    echo "  1. Pass a directory containing cloned repos"
    echo "  2. Set BITBUCKET_USERNAME and API_KEY to scan from Bitbucket"
    echo ""
    echo "Example:"
    echo "  $0 ~/repos"
    echo "  BITBUCKET_USERNAME=user API_KEY=key $0"
    exit 1
fi

# Summary
echo ""
echo "=== Summary ==="
echo "Total repos:    $TOTAL"
echo "Scanned:        $SCANNED"
echo "Skipped:        $SKIPPED (no package.json)"
echo "Errors:         $ERRORS"
echo ""
echo "Audit files saved to: $OUTPUT_DIR"
