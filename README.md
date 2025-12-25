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
| **AWS CLI** | 1 | Read-only AWS queries (WAF, ALB, ECS, etc.) |

### Streamlit Dashboard
Web interface with specialized AI agents:

| Agent | Description | Status |
|-------|-------------|--------|
| **DevOps** | Orchestrator for observability + user management | Active |
| **Coralogix** | Log analysis with AI-powered search | Active |
| **Bitbucket** | Repository management, PR reviews | Active |
| **CVE/Vulnerability** | Security vulnerability tracking | Active |
| **Confluence** | Documentation and knowledge base search | Planned |
| **Database** | Database queries and health monitoring | Planned |
| **HR** | HR policies and employee information | Planned |
| **Risk** | Underwriting and risk assessment | Planned |
| **Transaction** | Merchant transaction insights | Active |

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
│   │   ├── clippy_tools.py      # Tool definitions for Clippy
│   │   └── slack_bot/           # Slack bot (Clippy) - modular package
│   │       ├── bot.py           # Main bot logic & message handling
│   │       ├── tool_executor.py # Tool execution routing
│   │       ├── claude_tools.py  # Claude tool definitions
│   │       ├── prompt_enhancer.py # AI context extraction
│   │       ├── formatters.py    # Response formatting
│   │       ├── bedrock_client.py # Bedrock API client
│   │       ├── alerting.py      # Error alerting
│   │       └── metrics.py       # Request metrics
│   ├── streamlit/               # Streamlit UI + Agents
│   │   ├── app.py               # Main dashboard
│   │   ├── devops_agent.py      # DevOps orchestrator
│   │   ├── coralogix_agent.py   # Log analysis agent
│   │   ├── bitbucket_agent.py   # Repo management agent
│   │   ├── cve_agent.py         # CVE vulnerability tracking
│   │   ├── vulnerability_agent.py # Security vulnerability agent
│   │   ├── confluence_agent.py  # Documentation search (planned)
│   │   ├── database_agent.py    # Database queries (planned)
│   │   ├── hr_agent.py          # HR assistant (planned)
│   │   ├── risk_agent.py        # Risk assessment (planned)
│   │   └── transaction_agent.py # Transaction insights
│   └── lib/                     # Shared libraries (no framework deps)
│       ├── coralogix.py         # Coralogix API handlers
│       ├── bitbucket.py         # Bitbucket API handlers
│       ├── code_search.py       # Bedrock KB search
│       ├── atlassian.py         # Atlassian Admin API
│       ├── aws_cli.py           # Safe AWS CLI wrapper
│       ├── jira.py              # Jira API handlers
│       ├── pagerduty.py         # PagerDuty API handlers
│       ├── confluence.py        # Confluence API handlers
│       ├── config_loader.py     # Service registry & S3 config
│       ├── investigation_agent.py # Multi-step investigation orchestrator
│       └── utils/               # AWS clients, config, secrets
│           ├── aws.py           # AWS client factory
│           ├── config.py        # Configuration constants
│           ├── secrets.py       # Secrets Manager access
│           └── time_utils.py    # Time manipulation utilities
├── infra/                       # AWS CDK (JavaScript)
│   └── lib/
│       ├── ecs-fargate-stack.js     # ECS infrastructure
│       └── knowledge-base-stack.js  # Bedrock KB
├── scripts/
│   ├── deploy-to-ecs.sh         # Deploy to ECS Fargate
│   └── sync-repos-to-s3.py      # Sync code to KB bucket
├── tests/
│   ├── clippy_test_prompts.py   # Slack bot interactive test harness
│   └── test_clippy_tools.py     # Comprehensive tool tests
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
