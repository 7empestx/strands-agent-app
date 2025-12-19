# AWS ECS Fargate Deployment Guide

This guide explains how to deploy the Strands Agent App to AWS ECS Fargate.

## Architecture

```
Route53 (ai-agent.mrrobot.dev, mcp.mrrobot.dev)
    ↓
Application Load Balancer (ALB, port 80)
    ├→ /mcp* → MCP Server (2+ tasks, port 8080)
    └→ / → Streamlit (2+ tasks, port 8501)
```

**Benefits of ECS Fargate:**
- ✅ No server management (fully managed)
- ✅ Auto-scaling by CPU/memory
- ✅ Blue-green deployments (zero downtime)
- ✅ Health checks and auto-restart
- ✅ CloudWatch monitoring
- ✅ Better reliability than EC2 SSH deploys

---

## Prerequisites

1. **AWS Account** with dev environment configured
2. **AWS CLI** installed and configured with profile `dev`
3. **Docker** installed locally
4. **Node.js 18+** for CDK
5. **Appropriate IAM permissions** for:
   - ECR (push images)
   - ECS (update services, describe services)
   - CloudFormation (CDK deploy)
   - IAM (create roles)
   - EC2 (security groups)
   - Route53 (manage DNS)

---

## Initial Setup (One Time)

### 1. Deploy Infrastructure with CDK

```bash
cd infra
AWS_PROFILE=dev npx cdk deploy StrandsAgentECSStack --require-approval never
```

This creates:
- **ECR repositories** for Streamlit and MCP Server
- **ECS cluster** with Fargate launch type
- **Application Load Balancer** with target groups
- **Task definitions** for both services
- **CloudWatch log groups**
- **IAM roles** with proper permissions
- **Route53 DNS records** pointing to ALB

**Output**: The CDK will output:
```
Outputs:
  StreamlitRepoUri: <account-id>.dkr.ecr.us-east-1.amazonaws.com/mrrobot-streamlit
  McpServerRepoUri: <account-id>.dkr.ecr.us-east-1.amazonaws.com/mrrobot-mcp-server
  ClusterName: mrrobot-ai-core
```

---

## Deploying Code Changes

### Option 1: Automatic (Recommended)

Push to `main` branch triggers automatic deployment via Bitbucket Pipelines:

```bash
git push origin main
```

The pipeline will:
1. ✓ Run pre-commit checks and linting
2. ✓ Build Docker images (Streamlit + MCP Server)
3. ✓ Verify dependencies (e.g., Flask is installed)
4. ✓ Push to ECR with commit SHA tag
5. ✓ Update ECS services
6. ✓ Wait for deployment to stabilize

**Time**: ~5-7 minutes

### Option 2: Manual Pipeline Triggers

In Bitbucket, go to **Pipelines > Run pipeline** and select:

| Pipeline | Description |
|----------|-------------|
| `deploy-ecs` | Build images and deploy to ECS |
| `deploy-ecs-images-only` | Build and push images only |
| `deploy-infrastructure` | Deploy CDK stacks |
| `full-deploy` | CDK + Docker + ECS |

### Option 3: Local Deploy (Fallback)

Use this for deploying from your local machine:

```bash
./scripts/deploy-to-ecs.sh
```

This:
1. ✓ Builds Docker images (native architecture)
2. ✓ Pushes to ECR
3. ✓ Updates ECS services to use new images
4. ✓ Services rollout new tasks (blue-green)

**Time**: ~2-3 minutes

### Option 4: Full Deploy with CDK

Use this when changing infrastructure:

```bash
./scripts/deploy-to-ecs.sh --full
```

Or via pipeline: Select `full-deploy` from manual triggers.

**Time**: ~10-15 minutes

---

## Monitoring Deployment

### 1. Check Service Status

```bash
aws ecs describe-services \
  --cluster mrrobot-ai-core \
  --services mrrobot-streamlit mrrobot-mcp-server \
  --region us-east-1 \
  --profile dev
```

Look for:
- `desiredCount`: 2
- `runningCount`: 2 (both tasks running)
- `status`: ACTIVE
- No deployment issues in `deployments`

### 2. Verify Tasks Are Running

```bash
aws ecs list-tasks \
  --cluster mrrobot-ai-core \
  --service-name mrrobot-streamlit \
  --region us-east-1 \
  --profile dev
```

### 3. View Live Logs

**Streamlit:**
```bash
aws logs tail /ecs/mrrobot-streamlit --follow \
  --region us-east-1 --profile dev
```

**MCP Server:**
```bash
aws logs tail /ecs/mrrobot-mcp-server --follow \
  --region us-east-1 --profile dev
```

### 4. Check Load Balancer Health

```bash
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --region us-east-1 \
  --profile dev
```

All targets should show `TargetHealth.State: healthy`

---

## Accessing Services

### Streamlit UI
```
http://ai-agent.mrrobot.dev
```

### MCP Server (for IDE integration)
```
https://mcp.mrrobot.dev/sse
```

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "mrrobot-code-kb": {
      "url": "https://mcp.mrrobot.dev/sse",
      "transport": "sse"
    }
  }
}
```

---

## Troubleshooting

### Services Won't Start

1. **Check task logs:**
   ```bash
   aws logs tail /ecs/mrrobot-streamlit --follow --region us-east-1 --profile dev
   ```

2. **Check task definition:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition mrrobot-streamlit \
     --region us-east-1 --profile dev
   ```

3. **Common issues:**
   - ECR image doesn't exist → Re-run deploy script
   - Environment variables missing → Check task definition
   - Health check failing → Check app logs for startup errors

### Tasks Crashing on Deploy

1. **Check rolled back deployment:**
   ```bash
   aws ecs describe-services \
     --cluster mrrobot-ai-core \
     --services mrrobot-streamlit \
     --region us-east-1 --profile dev | jq '.services[0].deployments'
   ```

2. **Why it rolled back:**
   - Failed health check
   - Task exited with error
   - Insufficient memory/CPU

3. **Solution:**
   - Check logs for error
   - Fix code/config
   - Re-run `./scripts/deploy-to-ecs.sh`

### High Latency/Timeouts

1. **Check ALB target health:**
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn <tg-arn> \
     --region us-east-1 --profile dev
   ```

2. **Check task CPU/memory:**
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/ECS \
     --metric-name CPUUtilization \
     --dimensions Name=ServiceName,Value=mrrobot-streamlit Name=ClusterName,Value=mrrobot-ai-core \
     --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 300 \
     --statistics Average \
     --region us-east-1 --profile dev
   ```

3. **If CPU near 100%:**
   - Increase task CPU in CDK (currently 512 for Streamlit, 256 for MCP)
   - Edit `ecs-fargate-stack.js` and re-deploy with `--full`

### DNS Not Working

1. **Verify Route53 record:**
   ```bash
   aws route53 list-resource-record-sets \
     --hosted-zone-id Z00099541PMCE1WUL76PK \
     --query 'ResourceRecordSets[?Name==`ai-agent.mrrobot.dev.`]'
   ```

2. **Verify ALB DNS name:**
   ```bash
   aws elbv2 describe-load-balancers \
     --load-balancer-arns <alb-arn> \
     --region us-east-1 --profile dev
   ```

3. **Test DNS:**
   ```bash
   nslookup ai-agent.mrrobot.dev
   curl -v http://ai-agent.mrrobot.dev
   ```

---

## Scaling

### Manual Scaling

```bash
# Scale Streamlit to 4 tasks
aws ecs update-service \
  --cluster mrrobot-ai-core \
  --service mrrobot-streamlit \
  --desired-count 4 \
  --region us-east-1 --profile dev
```

### Auto-Scaling

Auto-scaling is already configured:
- **Min tasks**: 2
- **Max tasks**: 4
- **CPU trigger**: 70%
- **Memory trigger**: 80%

View auto-scaling status:
```bash
aws application-autoscaling describe-scalable-targets \
  --service-namespace ecs \
  --region us-east-1 --profile dev
```

---

## Rollback

### Rollback to Previous Image

If deployment goes wrong:

```bash
# Get previous task definition revision
aws ecs list-task-definitions \
  --family-prefix mrrobot-streamlit \
  --sort DESC \
  --region us-east-1 --profile dev

# Update service to use previous revision
aws ecs update-service \
  --cluster mrrobot-ai-core \
  --service mrrobot-streamlit \
  --task-definition mrrobot-streamlit:2 \
  --region us-east-1 --profile dev
```

ECS keeps the last 5 revisions of each task definition.

---

## Cost Estimation

**Monthly cost (rough estimate):**

| Resource | Qty | Unit Cost | Monthly |
|----------|-----|-----------|---------|
| Streamlit (512 CPU, 1GB mem) | 2 tasks | $0.0284/hr | ~$41 |
| MCP Server (256 CPU, 768MB mem) | 2 tasks | $0.0142/hr | ~$21 |
| ALB | 1 | $16.20 | $16.20 |
| Data transfer | - | $0.02/GB | ~$5-10 |
| CloudWatch logs | - | $0.50/GB | ~$2-5 |
| **Total** | | | **~$85-95/month** |

*This is cheaper than the previous EC2 setup (~$150-200/month) and more reliable.*

---

## Next Steps

1. ✓ Run `./scripts/deploy-to-ecs.sh --full` to deploy
2. ✓ Monitor logs and verify services are running
3. ✓ Test at http://ai-agent.mrrobot.dev
4. ✓ Delete EC2 instance (old deployment) once everything works
5. ✓ Update team documentation with new URLs

---

## Additional Resources

- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/best_practices.html)
- [Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
- [ECS CloudFormation Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_ECS.html)
- [Application Load Balancer Guide](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
