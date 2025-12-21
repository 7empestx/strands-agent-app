# MrRobot AI Core

AI-powered DevOps platform with **Slack Bot (Clippy)**, **MCP Server**, and **Streamlit Dashboard** using **Strands SDK** + **Claude Sonnet 4 on Amazon Bedrock**.

## Features

### Slack Bot (Clippy)
AI assistant in `#devops` Slack channel that can:
- Search logs in Coralogix
- Check pipeline/deploy status in Bitbucket
- Review PRs and explain failures
- Query AWS infrastructure (ALBs, WAF, ECS)
- Check CloudWatch alarms
- Search code across 254 repositories

### MCP Server (30+ Tools)
Universal AI tool server for Cursor, Claude Code, and other MCP-compatible IDEs:

| Category | Tools | Description |
|----------|-------|-------------|
| **Code Search** | 7 | Semantic search across 254 repos via Bedrock KB |
| **Coralogix** | 5 | Log analysis, error tracking, service health |
| **Atlassian** | 12 | User/group management for onboarding/offboarding |
| **Bitbucket** | 6 | PRs, pipelines, repos, branches, commits |
| **CloudWatch** | 7 | Metrics, alarms, logs |
| **AWS CLI** | 1 | Read-only AWS queries (WAF, ALB, ECS, etc.) |

### Streamlit Dashboard
Web interface with specialized AI agents:

| Agent | Description |
|-------|-------------|
| **DevOps** | Orchestrator for observability + user management |
| **Coralogix** | Log analysis with AI-powered search |
| **Bitbucket** | Repository management, PR reviews |
| **CVE/Vulnerability** | Security vulnerability tracking |

## Quick Start

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

### Local Development

```bash
# MCP Server + Slack Bot
cd src/mcp_server
python server.py --http --port 8080 --slack

# Streamlit Dashboard
cd src/streamlit
AWS_PROFILE=dev streamlit run app.py
```

### Test Slack Bot Locally

```bash
# Interactive mode
python tests/clippy_test_prompts.py -i

# Run all test prompts
python tests/clippy_test_prompts.py -s
```

## Project Structure

```
strands-agent-app/
├── src/
│   ├── mcp_server/              # MCP Server + Slack Bot
│   │   ├── server.py            # FastMCP server (30+ tools)
│   │   └── slack_bot.py         # Slack bot (Clippy)
│   ├── streamlit/               # Streamlit UI + Agents
│   │   ├── app.py               # Main dashboard
│   │   ├── devops_agent.py      # DevOps orchestrator
│   │   ├── coralogix_agent.py   # Log analysis agent
│   │   ├── bitbucket_agent.py   # Repo management agent
│   │   └── ...                  # Other specialized agents
│   └── lib/                     # Shared libraries (no framework deps)
│       ├── coralogix.py         # Coralogix API handlers
│       ├── bitbucket.py         # Bitbucket API handlers
│       ├── cloudwatch.py        # CloudWatch handlers
│       ├── code_search.py       # Bedrock KB search
│       ├── atlassian.py         # Atlassian Admin API
│       ├── aws_cli.py           # Safe AWS CLI wrapper
│       └── utils/               # AWS clients, config, secrets
├── infra/                       # AWS CDK (JavaScript)
│   └── lib/
│       ├── ecs-fargate-stack.js     # ECS infrastructure
│       └── knowledge-base-stack.js  # Bedrock KB
├── scripts/
│   ├── deploy-to-ecs.sh         # Deploy to ECS Fargate
│   └── sync-repos-to-s3.py      # Sync code to KB bucket
├── tests/
│   └── clippy_test_prompts.py   # Slack bot test harness
├── Dockerfile.mcp               # MCP Server container
├── Dockerfile.streamlit         # Streamlit container
└── bitbucket-pipelines.yml      # CI/CD pipeline
```

## Infrastructure

| Resource | Value |
|----------|-------|
| **ECS Cluster** | `mrrobot-ai-core` |
| **MCP Server** | https://mcp.mrrobot.dev/sse |
| **Streamlit** | https://ai-agent.mrrobot.dev |
| **Knowledge Base ID** | `SAJJWYFTNG` |
| **AWS Account** | `720154970215` (dev) |
| **Region** | `us-east-1` |

## Deployment

### Automatic (Recommended)
Push to `main` branch triggers automatic deployment via Bitbucket Pipelines:
```bash
git push origin main
```

### Manual Deploy
```bash
# Build and deploy to ECS
./scripts/deploy-to-ecs.sh

# Full deploy (includes CDK infrastructure)
./scripts/deploy-to-ecs.sh --full
```

### View Logs
```bash
# MCP Server + Slack Bot logs
AWS_PROFILE=dev aws logs tail /ecs/mrrobot-mcp-server --follow --region us-east-1

# Streamlit logs
AWS_PROFILE=dev aws logs tail /ecs/mrrobot-streamlit --follow --region us-east-1
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Claude Sonnet 4 (Bedrock) |
| AI Agents | Strands SDK |
| MCP Server | FastMCP (Anthropic SDK) |
| Vector Store | OpenSearch Serverless |
| Knowledge Base | Amazon Bedrock KB |
| Frontend | Streamlit |
| Compute | ECS Fargate (ARM64/Graviton) |
| Infrastructure | AWS CDK (JavaScript) |
| CI/CD | Bitbucket Pipelines |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ECS Fargate                              │
│  ┌─────────────────────────┐  ┌─────────────────────────────┐   │
│  │   MCP Server Container   │  │   Streamlit Container       │   │
│  │  ┌───────────────────┐   │  │  ┌─────────────────────┐   │   │
│  │  │   server.py       │   │  │  │      app.py         │   │   │
│  │  │   (FastMCP)       │   │  │  │   (Dashboard)       │   │   │
│  │  └───────────────────┘   │  │  └─────────────────────┘   │   │
│  │  ┌───────────────────┐   │  │  ┌─────────────────────┐   │   │
│  │  │   slack_bot.py    │   │  │  │   *_agent.py        │   │   │
│  │  │   (Clippy)        │   │  │  │   (Strands Agents)  │   │   │
│  │  └───────────────────┘   │  │  └─────────────────────┘   │   │
│  └───────────┬──────────────┘  └──────────────┬─────────────┘   │
│              │                                 │                  │
│              └────────────┬───────────────────┘                  │
│                           │                                       │
│                    ┌──────▼──────┐                               │
│                    │   src/lib   │                               │
│                    │  (shared)   │                               │
│                    └──────┬──────┘                               │
└───────────────────────────┼─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   Coralogix   │  │   Bitbucket   │  │  Bedrock KB   │
│     API       │  │     API       │  │  (254 repos)  │
└───────────────┘  └───────────────┘  └───────────────┘
```

## Documentation

- [CLAUDE.md](./CLAUDE.md) - Project context for AI assistants
- [DEPLOYMENT-ECS.md](./DEPLOYMENT-ECS.md) - Full ECS deployment guide
