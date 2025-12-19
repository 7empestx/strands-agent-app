# MrRobot AI Core

AI-powered platform for DevOps, log analysis, and code search using **Strands SDK** + **Claude Sonnet on Amazon Bedrock**.

## Features

### AI Agents (Streamlit Dashboard)
Specialized agents for different operational needs:

| Agent | Description |
|-------|-------------|
| **Coralogix** | Log analysis with AI-powered search, PCI compliance checks (CVV/PAN detection) |
| **Bitbucket** | Repository management, PR reviews, pipeline status |
| **CloudWatch** | AWS log and metrics analysis |
| **CVE/Vulnerability** | Security vulnerability scanning and CVE tracking |
| **Database** | Database query assistance |
| **DevOps** | Infrastructure and deployment help |
| **Risk** | Risk assessment and analysis |

### Code Knowledge Base (MCP Server)
Search 254 MrRobot repositories (17,169 documents) via AI-powered semantic search:
- Integrated with Cursor, Claude Code, and other MCP-compatible IDEs
- Natural language queries: "How does authentication work in the API?"
- 4 tools: `search_mrrobot_repos`, `get_file_content`, `list_repos`, `get_kb_info`
- Backed by Amazon Bedrock Knowledge Base + OpenSearch Serverless

## Quick Start

### Local Development
```bash
cd ~/Mine/mrrobot-ai-core
source venv/bin/activate
AWS_PROFILE=dev streamlit run app.py
```
Open http://localhost:8501

### Connect AI IDE to MCP Server

**Requirement:** Must be connected to VPN.

#### Cursor
Add to `~/.cursor/mcp.json`:
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

#### Claude Code
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

## Infrastructure

| Resource | Value |
|----------|-------|
| **ECS Cluster** | `mrrobot-ai-core` |
| Streamlit URL | http://ai-agent.mrrobot.dev |
| MCP Server URL | https://mcp.mrrobot.dev/sse |
| Knowledge Base ID | `SAJJWYFTNG` |
| AWS Account | `720154970215` (dev) |
| Region | `us-east-1` |

## Deployment

### Automatic (Recommended)
Push to `main` branch triggers automatic deployment:
```bash
git push origin main
```
This will:
1. Run pre-commit checks and linting
2. Build Docker images (Streamlit + MCP Server)
3. Push to ECR
4. Deploy to ECS Fargate

### Manual Triggers (Bitbucket Pipelines)
| Pipeline | Description |
|----------|-------------|
| `deploy-ecs` | Build images and deploy to ECS |
| `deploy-ecs-images-only` | Build and push images only |
| `deploy-infrastructure` | Deploy CDK stacks |
| `full-deploy` | CDK + Docker + ECS |

### Local Deployment
```bash
# Deploy to ECS from local machine
./scripts/deploy-to-ecs.sh

# Deploy CDK infrastructure
cd infra && npm install
AWS_PROFILE=dev npx cdk deploy StrandsAgentECSStack
```

### Monitoring
```bash
# View ECS logs
aws logs tail /ecs/mrrobot-mcp-server --follow --region us-east-1 --profile dev
aws logs tail /ecs/mrrobot-streamlit --follow --region us-east-1 --profile dev

# Check service status
aws ecs describe-services --cluster mrrobot-ai-core \
  --services mrrobot-streamlit mrrobot-mcp-server \
  --region us-east-1 --profile dev
```

## Project Structure

```
mrrobot-ai-core/
├── app.py                    # Streamlit frontend
├── Dockerfile.streamlit      # Streamlit container
├── Dockerfile.mcp            # MCP server container
├── agents/                   # AI agents
│   ├── coralogix_agent.py    # Log analysis + PCI compliance
│   ├── bitbucket_agent.py    # Repository management
│   ├── cloudwatch_agent.py   # AWS logs/metrics
│   ├── cve_agent.py          # CVE tracking
│   └── ...
├── mcp-servers/
│   └── bedrock-kb-server.py  # MCP server for KB search
├── infra/                    # AWS CDK (JavaScript)
│   └── lib/
│       ├── ecs-fargate-stack.js      # ECS Fargate infrastructure
│       ├── knowledge-base-stack.js   # Bedrock KB infrastructure
│       └── constants/
├── scripts/
│   ├── deploy-to-ecs.sh      # Deploy to ECS Fargate
│   └── sync-repos-to-s3.py   # Sync code to KB bucket
├── bitbucket-pipelines.yml   # CI/CD pipeline
└── requirements.txt          # Python dependencies
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| AI Agent | Strands SDK |
| LLM | Claude Sonnet 4 (Bedrock) |
| Vector Store | OpenSearch Serverless |
| Knowledge Base | Amazon Bedrock KB |
| Frontend | Streamlit |
| Compute | ECS Fargate (ARM64/Graviton) |
| Infrastructure | AWS CDK (JavaScript) |
| CI/CD | Bitbucket Pipelines |
| Container Registry | Amazon ECR |
| MCP Transport | Server-Sent Events (SSE) |

## Documentation

- [DEPLOYMENT-ECS.md](./DEPLOYMENT-ECS.md) - Full ECS deployment guide
- [CLAUDE.md](./CLAUDE.md) - Project context for AI assistants
- [DEMO.md](./DEMO.md) - Demo walkthrough and architecture
