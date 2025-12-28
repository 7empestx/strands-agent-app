#!/bin/bash
# Deploy to AWS ECS Fargate
# Usage: ./scripts/deploy-to-ecs.sh [--full]
# --full: Full deployment (CDK deploy + image push + service update)
# Without flag: Only pushes images and updates services (faster for code changes)
#
# NOTE: Streamlit has been deprecated. The React dashboard is now served
# from the MCP server at the root URL (ai-agent.mrrobot.dev).

set -e

# Configuration
AWS_REGION="us-east-1"
AWS_PROFILE="${AWS_PROFILE:-dev}"
# Determine environment suffix from AWS_PROFILE
ENV_SUFFIX="${AWS_PROFILE:-dev}"
CLUSTER_NAME="mrrobot-ai-core-${ENV_SUFFIX}"
MCP_SERVICE="mrrobot-mcp-server-${ENV_SUFFIX}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE")
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

MCP_IMAGE_URI="${REGISTRY}/mrrobot-mcp-server:latest"

echo "=========================================================================="
echo "ECS Fargate Deployment"
echo "=========================================================================="
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo "Profile: $AWS_PROFILE"
echo "Cluster: $CLUSTER_NAME"
echo ""
echo "Deploying: MCP Server + React Dashboard (combined)"
echo "Note: Building native arm64 images (Fargate Graviton)"
echo ""

# =========================================================================
# Step 1: Authenticate with ECR
# =========================================================================
echo "[1/4] Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" --profile "$AWS_PROFILE" | \
  docker login --username AWS --password-stdin "$REGISTRY"
echo "✓ ECR authentication successful"
echo ""

# =========================================================================
# Step 2: Build MCP Server + Dashboard image
# =========================================================================
echo "[2/4] Building MCP Server + Dashboard Docker image..."
echo "      (This includes React dashboard build)"

# Extract NPM token for private registry (@mrrobot packages)
NPM_TOKEN=$(grep -o '_authToken=[^[:space:]]*' ~/.npmrc | head -1 | cut -d'=' -f2)
if [ -z "$NPM_TOKEN" ]; then
  echo "Warning: NPM_TOKEN not found in ~/.npmrc - private packages may fail to install"
fi

docker build \
  -f "$LOCAL_DIR/Dockerfile.mcp" \
  --build-arg NPM_TOKEN="$NPM_TOKEN" \
  -t mrrobot-mcp-server:latest \
  -t "$MCP_IMAGE_URI" \
  "$LOCAL_DIR"
echo "✓ MCP Server image built (with dashboard)"
echo ""

# =========================================================================
# Step 3: Push image to ECR
# =========================================================================
echo "[3/4] Pushing image to ECR..."
docker push "$MCP_IMAGE_URI"
echo "✓ Image pushed to ECR"
echo ""

# =========================================================================
# Step 4: Update ECS service
# =========================================================================
echo "[4/4] Updating ECS service..."

# Force new deployment for MCP Server
echo "  → Updating MCP Server service..."
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$MCP_SERVICE" \
  --desired-count 1 \
  --force-new-deployment \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  > /dev/null

echo "✓ ECS service updated"
echo ""

# =========================================================================
# Step 5: Wait for deployment
# =========================================================================
echo "[5/6] Waiting for ECS task to stabilize..."
echo ""
echo "Current task count:"
aws ecs describe-services \
  --cluster "$CLUSTER_NAME" \
  --services "$MCP_SERVICE" \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --query 'services[*].{Service:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
  --output table

echo ""
echo "Waiting for old tasks to drain (this may take 1-2 minutes)..."
echo "You can monitor in AWS Console: https://console.aws.amazon.com/ecs/home?region=${AWS_REGION}#/clusters/${CLUSTER_NAME}/services"
echo ""

# Wait for running count to match desired count
MAX_WAIT=180
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  MCP_RUNNING=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$MCP_SERVICE" \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --query 'services[0].runningCount' \
    --output text 2>/dev/null)

  if [ "$MCP_RUNNING" == "1" ]; then
    echo "✓ Service stabilized at 1 task"
    break
  fi

  echo "  ... waiting (${WAITED}s) - running: ${MCP_RUNNING}"
  sleep 10
  WAITED=$((WAITED + 10))
done

if [ $WAITED -ge $MAX_WAIT ]; then
  echo "⚠ Timeout waiting for task to stabilize. Please check ECS console."
fi

echo ""

# =========================================================================
# Step 6: Verify deployment
# =========================================================================
echo "[6/6] Verifying deployment..."

# Get the digest we just pushed
PUSHED_DIGEST=$(aws ecr describe-images \
  --repository-name mrrobot-mcp-server \
  --image-ids imageTag=latest \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --query 'imageDetails[0].imageDigest' \
  --output text)
echo "  → Pushed image digest: ${PUSHED_DIGEST:0:20}..."

# Wait for ECS to start new tasks with the new image
echo "  → Waiting for ECS to deploy new task (up to 120s)..."
MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  # Get running task's image digest
  TASK_ARN=$(aws ecs list-tasks \
    --cluster "$CLUSTER_NAME" \
    --service-name "$MCP_SERVICE" \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --query 'taskArns[0]' \
    --output text 2>/dev/null)

  if [ -n "$TASK_ARN" ] && [ "$TASK_ARN" != "None" ]; then
    RUNNING_DIGEST=$(aws ecs describe-tasks \
      --cluster "$CLUSTER_NAME" \
      --tasks "$TASK_ARN" \
      --region "$AWS_REGION" \
      --profile "$AWS_PROFILE" \
      --query 'tasks[0].containers[0].imageDigest' \
      --output text 2>/dev/null)

    if [ "$RUNNING_DIGEST" == "$PUSHED_DIGEST" ]; then
      echo "  ✓ New image is running!"
      break
    fi
  fi

  sleep 10
  WAITED=$((WAITED + 10))
  echo "    ... still waiting (${WAITED}s)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
  echo "  ⚠ Timeout waiting for new task. Check ECS console."
  echo "    Pushed:  $PUSHED_DIGEST"
  echo "    Running: $RUNNING_DIGEST"
fi

echo ""

# =========================================================================
# Summary
# =========================================================================
echo "=========================================================================="
echo "Deployment Complete!"
echo "=========================================================================="
echo ""
echo "Dashboard URL: https://ai-agent.mrrobot.dev"
echo "MCP Server URL: https://mcp.mrrobot.dev/sse"
echo ""
echo "Pushed image:  ${PUSHED_DIGEST:0:30}..."
echo "Running image: ${RUNNING_DIGEST:0:30}..."
echo ""
echo "To view logs:"
echo "  aws logs tail /ecs/mrrobot-mcp-server --follow --region $AWS_REGION --profile $AWS_PROFILE"
echo ""

# =========================================================================
# Full CDK Deployment (if --full flag)
# =========================================================================
if [[ "$1" == "--full" ]]; then
  echo ""
  echo "Running full CDK deployment (infrastructure + images)..."
  cd "$LOCAL_DIR/infra"

  AWS_PROFILE="$AWS_PROFILE" npx cdk deploy StrandsAgentECSStack \
    --region "$AWS_REGION" \
    --require-approval never

  cd "$LOCAL_DIR"
  echo ""
  echo "✓ Full deployment complete!"
fi
