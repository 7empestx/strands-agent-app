#!/bin/bash
# Pre-commit validation script
# Run this before committing to catch issues early
# Usage: ./scripts/pre-commit-check.sh

set -e

# Change to project root (parent of scripts/)
cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Pre-Commit Validation Check"
echo "========================================"
echo ""

FAILED=0

# Function to run a check
run_check() {
    local name="$1"
    local cmd="$2"

    echo -n "Checking $name... "
    if eval "$cmd" > /tmp/check_output.txt 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        cat /tmp/check_output.txt
        FAILED=1
        return 1
    fi
}

# 1. Check Python syntax (quick compile check)
echo ""
echo "=== Python Syntax Checks ==="
run_check "Python syntax (src/)" "python -m py_compile src/mcp_server/server.py src/mcp_server/auth.py src/mcp_server/chatbot.py src/mcp_server/alert_enhancer.py 2>&1"

# 2. Run flake8 linting
echo ""
echo "=== Flake8 Linting ==="
run_check "flake8" "flake8 . --max-line-length=120 --extend-ignore=E203,W503,E501,F541,F841,E302,E305,E402 --exclude=venv,.venv,infra,node_modules,web-dashboard/node_modules"

# 3. Run black formatting check (don't modify, just check)
echo ""
echo "=== Black Formatting ==="
run_check "black" "black --check --line-length=120 src/ scripts/*.py 2>&1"

# 4. Run isort import sorting check
echo ""
echo "=== Import Sorting (isort) ==="
run_check "isort" "isort --check-only --profile=black --line-length=120 src/ scripts/*.py 2>&1"

# 5. Run bandit security check
echo ""
echo "=== Security Check (bandit) ==="
if command -v bandit &> /dev/null; then
    run_check "bandit" "bandit -lll -iii -r src/ --exclude venv,.venv,infra,tests,scripts 2>&1"
else
    echo -e "${YELLOW}⚠ bandit not installed (pip install bandit)${NC}"
fi

# 6. Check YAML files
echo ""
echo "=== YAML Validation ==="
run_check "YAML syntax" "python -c \"import yaml; yaml.safe_load(open('.pre-commit-config.yaml'))\" 2>&1"

# 7. Check JSON files
echo ""
echo "=== JSON Validation ==="
run_check "JSON syntax (cdk.context.json)" "python -c \"import json; json.load(open('infra/cdk.context.json'))\" 2>&1"

# 8. Check for large files (>1MB)
echo ""
echo "=== Large File Check ==="
run_check "No large files staged" "! git diff --cached --name-only | xargs -I{} sh -c 'test -f \"{}\" && test \$(stat -f%z \"{}\" 2>/dev/null || stat -c%s \"{}\" 2>/dev/null) -gt 1000000 && echo \"Large file: {}\"' | grep -q 'Large file'"

# 9. Check for secrets/credentials (skip variable references like $TOKEN)
echo ""
echo "=== Secret Detection ==="
run_check "No secrets detected" "! git diff --cached | grep -iE '(password|secret|api_key|apikey|credential).*=.*[\"'\''][A-Za-z0-9+/=]{20,}[\"'\'']' | grep -vE '(get_secret|SECRET_KEY|_SECRET|secret_name|SecretString|secretsmanager|\\\$[A-Z_]+)'"

# 10. Check requirements.txt is valid
echo ""
echo "=== Requirements Validation ==="
run_check "requirements.txt syntax" "pip check 2>&1 || true"

# 11. Run pre-commit hooks on staged files
echo ""
echo "=== Pre-commit Hooks ==="
if git diff --cached --name-only | head -1 > /dev/null 2>&1; then
    run_check "pre-commit (staged files)" "pre-commit run --files \$(git diff --cached --name-only | tr '\n' ' ') 2>&1"
else
    run_check "pre-commit (all changed)" "pre-commit run --all-files 2>&1"
fi

# 12. Check Docker build (optional, slow)
echo ""
echo "=== Docker Build Check ==="
if command -v docker &> /dev/null; then
    echo -n "Checking Dockerfile.mcp syntax... "
    if docker build --check -f Dockerfile.mcp . > /dev/null 2>&1 || docker build -f Dockerfile.mcp . --target dashboard-builder --no-cache --progress=plain 2>&1 | head -20 | grep -q "error" && false || true; then
        echo -e "${YELLOW}⚠ SKIPPED (use --docker to test)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Docker not available${NC}"
fi

# 13. Check CDK synth (optional - slow, run with --cdk flag)
echo ""
echo "=== CDK Synth Check ==="
if [[ "$*" == *"--cdk"* ]]; then
    if command -v node &> /dev/null && [ -d "infra" ]; then
        run_check "CDK synthesis" "(cd infra && npm run cdk synth --quiet 2>&1)"
    else
        echo -e "${YELLOW}⚠ Node.js not available${NC}"
    fi
else
    echo -e "${YELLOW}⚠ SKIPPED (run with --cdk flag to test)${NC}"
fi

# Summary
echo ""
echo "========================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All checks passed! Safe to commit.${NC}"
    echo "========================================"
    echo ""
    echo "Next steps:"
    echo "  git add -A"
    echo "  git commit -m 'Your commit message'"
    echo "  git push"
    exit 0
else
    echo -e "${RED}Some checks failed. Fix issues before committing.${NC}"
    echo "========================================"
    exit 1
fi
