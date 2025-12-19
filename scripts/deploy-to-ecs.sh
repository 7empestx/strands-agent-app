#!/bin/bash
# Deploy to AWS ECS Fargate
# Usage: ./scripts/deploy-to-ecs.sh [--full]
# --full: Full deployment (CDK deploy + image push + service update)
# Without flag: Only pushes images and updates services (faster for code changes)

set -e

# Configuration
AWS_REGION="us-east-1"
AWS_PROFILE="${AWS_PROFILE:-dev}"
CLUSTER_NAME="mrrobot-ai-core"
STREAMLIT_SERVICE="mrrobot-streamlit"
MCP_SERVICE="mrrobot-mcp-server"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE")
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

STREAMLIT_IMAGE_URI="${REGISTRY}/mrrobot-streamlit:latest"
MCP_IMAGE_URI="${REGISTRY}/mrrobot-mcp-server:latest"

echo "=========================================================================="
echo "ECS Fargate Deployment"
echo "=========================================================================="
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo "Profile: $AWS_PROFILE"
echo "Cluster: $CLUSTER_NAME"
echo ""
echo "Note: Building native arm64 images (Fargate Graviton)"
echo "      No cross-compilation needed!"
echo ""

# =========================================================================
# Step 1: Authenticate with ECR
# =========================================================================
echo "[1/5] Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" --profile "$AWS_PROFILE" | \
  docker login --username AWS --password-stdin "$REGISTRY"
echo "✓ ECR authentication successful"
echo ""

# =========================================================================
# Step 2: Build Streamlit image
# =========================================================================
echo "[2/5] Building Streamlit Docker image..."
docker build \
  -f "$LOCAL_DIR/Dockerfile.streamlit" \
  -t mrrobot-streamlit:latest \
  -t "$STREAMLIT_IMAGE_URI" \
  "$LOCAL_DIR"
echo "✓ Streamlit image built"
echo ""

# =========================================================================
# Step 3: Build MCP Server image
# =========================================================================
echo "[3/5] Building MCP Server Docker image..."
docker build \
  -f "$LOCAL_DIR/Dockerfile.mcp" \
  -t mrrobot-mcp-server:latest \
  -t "$MCP_IMAGE_URI" \
  "$LOCAL_DIR"
echo "✓ MCP Server image built"
echo ""

# =========================================================================
# Step 4: Push images to ECR
# =========================================================================
echo "[4/5] Pushing images to ECR..."
echo "  → Pushing Streamlit..."
docker push "$STREAMLIT_IMAGE_URI"
echo "  → Pushing MCP Server..."
docker push "$MCP_IMAGE_URI"
echo "✓ Images pushed to ECR"
echo ""

# =========================================================================
# Step 5: Update ECS services
# =========================================================================
echo "[5/5] Updating ECS services..."

# Force new deployment for Streamlit
echo "  → Updating Streamlit service..."
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$STREAMLIT_SERVICE" \
  --force-new-deployment \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  > /dev/null

# Force new deployment for MCP Server
echo "  → Updating MCP Server service..."
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$MCP_SERVICE" \
  --force-new-deployment \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  > /dev/null

echo "✓ ECS services updated"
echo ""

# =========================================================================
# Summary
# =========================================================================
echo "=========================================================================="
echo "Deployment Complete!"
echo "=========================================================================="
echo ""
echo "Streamlit URL: http://ai-agent.mrrobot.dev:8501"
echo "MCP Server URL: https://mcp.mrrobot.dev/sse"
echo ""
echo "To check deployment status:"
echo "  aws ecs describe-services \\
    --cluster $CLUSTER_NAME \\
    --services $STREAMLIT_SERVICE $MCP_SERVICE \\
    --region $AWS_REGION \\
    --profile $AWS_PROFILE"
echo ""
echo "To view logs:"
echo "  Streamlit: aws logs tail /ecs/mrrobot-streamlit --follow --region $AWS_REGION --profile $AWS_PROFILE"
echo "  MCP:       aws logs tail /ecs/mrrobot-mcp-server --follow --region $AWS_REGION --profile $AWS_PROFILE"
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
