# MrRobot AI Core

AI-powered platform for DevOps, log analysis, code search, and employee onboarding/offboarding using **Strands SDK** + **Claude Sonnet on Amazon Bedrock**.

## Features

### MCP Server (30 Tools)
Universal AI tool server for Cursor, Claude Code, and other MCP-compatible IDEs:

| Category | Tools | Description |
|----------|-------|-------------|
| **Code Search** | 7 | Semantic search across 254 repos (17,169 docs) via Bedrock KB |
| **Coralogix** | 5 | Log analysis, error tracking, service health |
| **Atlassian** | 12 | User/group management for onboarding/offboarding |
| **Bitbucket** | 6 | PRs, pipelines, repos, branches, commits |

### AI Agents (Streamlit Dashboard)
Specialized agents for different operational needs:

| Agent | Description |
|-------|-------------|
| **DevOps** | Orchestrator for observability + onboarding/offboarding |
| **Coralogix** | Log analysis with AI-powered search, PCI compliance checks |
| **Bitbucket** | Repository management, PR reviews, pipeline status |
| **CVE/Vulnerability** | Security vulnerability scanning and CVE tracking |

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

## MCP Tools Reference

### Code Search (Bedrock Knowledge Base)
| Tool | Description |
|------|-------------|
| `search_mrrobot_repos` | Semantic search across all 254 repos |
| `search_in_repo` | Search within a specific repository |
| `find_similar_code` | Find similar code patterns |
| `get_file_content` | Fetch full file from Bitbucket |
| `list_repos` | List indexed repositories |
| `search_by_file_type` | Search specific file types (serverless.yml, .tf) |
| `get_kb_info` | Knowledge base stats and tips |

### Coralogix (Log Analysis)
| Tool | Description |
|------|-------------|
| `coralogix_discover_services` | Discover available log groups |
| `coralogix_get_recent_errors` | Get recent errors by service |
| `coralogix_get_service_logs` | Get logs for a specific service |
| `coralogix_search_logs` | Execute custom DataPrime queries |
| `coralogix_get_service_health` | Service health overview |

### Atlassian (User/Group Management)
| Tool | Description |
|------|-------------|
| `atlassian_list_users` | List all users |
| `atlassian_suspend_user` | Suspend user (offboarding) |
| `atlassian_restore_user` | Restore suspended user |
| `atlassian_remove_user` | Remove user from directory |
| `atlassian_list_groups` | List all groups |
| `atlassian_create_group` | Create new group |
| `atlassian_delete_group` | Delete group |
| `atlassian_add_user_to_group` | Add user to group (onboarding) |
| `atlassian_remove_user_from_group` | Remove from group (offboarding) |
| `atlassian_grant_group_access` | Grant product access |
| `atlassian_revoke_group_access` | Revoke product access |
| `atlassian_get_directories` | Get organization directories |

### Bitbucket (Repository & CI/CD)
| Tool | Description |
|------|-------------|
| `bitbucket_list_prs` | List pull requests |
| `bitbucket_pipeline_status` | Get CI/CD pipeline status |
| `bitbucket_repo_info` | Repository details |
| `bitbucket_list_repos` | List all repositories |
| `bitbucket_commit_info` | Get commit details |
| `bitbucket_list_branches` | List branches in a repo |

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
├── agents/                   # AI agents (Strands SDK)
│   ├── devops_agent.py       # Orchestrator agent
│   ├── bitbucket_agent.py    # Repository management
│   ├── coralogix_agent.py    # Log analysis
│   ├── cve_agent.py          # CVE tracking
│   └── ...
├── mcp-servers/
│   ├── server.py             # Main MCP server (FastMCP)
│   └── tools/                # MCP tool implementations
│       ├── bedrock_kb.py     # Code search tools
│       ├── coralogix.py      # Log analysis tools
│       ├── atlassian.py      # User/group management
│       └── bitbucket.py      # Bitbucket API tools
├── utils/                    # Shared utilities
│   ├── config.py             # Centralized configuration
│   ├── aws.py                # AWS client factories
│   └── secrets.py            # Secrets Manager access
├── infra/                    # AWS CDK (JavaScript)
│   └── lib/
│       ├── ecs-fargate-stack.js      # ECS infrastructure
│       └── knowledge-base-stack.js   # Bedrock KB
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
| MCP Server | FastMCP (Anthropic SDK) |
| Vector Store | OpenSearch Serverless |
| Knowledge Base | Amazon Bedrock KB |
| Frontend | Streamlit |
| Compute | ECS Fargate (ARM64/Graviton) |
| Infrastructure | AWS CDK (JavaScript) |
| CI/CD | Bitbucket Pipelines |
| Container Registry | Amazon ECR |

## Documentation

- [DEPLOYMENT-ECS.md](./DEPLOYMENT-ECS.md) - Full ECS deployment guide
- [CLAUDE.md](./CLAUDE.md) - Project context for AI assistants
- [DEMO.md](./DEMO.md) - Demo walkthrough and architecture
