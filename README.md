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
      "url": "http://mcp.mrrobot.dev:8080/sse",
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
      "url": "http://mcp.mrrobot.dev:8080/sse",
      "transport": "sse"
    }
  }
}
```

## Infrastructure

| Resource | Value |
|----------|-------|
| EC2 Elastic IP | `34.202.219.55` |
| Streamlit URL | http://ai-agent.mrrobot.dev:8501 |
| MCP Server URL | http://mcp.mrrobot.dev:8080/sse |
| Knowledge Base ID | `SAJJWYFTNG` |
| AWS Account | `720154970215` (dev) |
| Region | `us-east-1` |

## Deployment

### Deploy App to EC2
```bash
# Code only
./scripts/deploy-to-ec2.sh

# Code + restart services
./scripts/deploy-to-ec2.sh --start
```

### Deploy Infrastructure (CDK)
```bash
cd infra && npm install

# EC2 stack
AWS_PROFILE=dev npx cdk deploy StrandsAgentStack

# Knowledge Base stack
AWS_PROFILE=dev npx cdk deploy CodeKnowledgeBaseStack
```

## Project Structure

```
mrrobot-ai-core/
├── app.py                    # Streamlit frontend
├── agents/                   # AI agents
│   ├── coralogix_agent.py    # Log analysis + PCI compliance
│   ├── bitbucket_agent.py    # Repository management
│   ├── cloudwatch_agent.py   # AWS logs/metrics
│   ├── cve_agent.py          # CVE tracking
│   ├── vulnerability_agent.py # Security scanning
│   ├── database_agent.py     # Database queries
│   ├── devops_agent.py       # DevOps assistance
│   └── risk_agent.py         # Risk analysis
├── mcp-servers/
│   └── bedrock-kb-server.py  # MCP server for KB search
├── infra/                    # AWS CDK (JavaScript)
│   ├── bin/app.js
│   └── lib/
│       ├── strands-agent-stack.js    # EC2 infrastructure
│       ├── knowledge-base-stack.js   # Bedrock KB infrastructure
│       └── constants/
│           └── aws-accounts.js       # Shared AWS config
├── scripts/
│   ├── deploy-to-ec2.sh      # Deploy app to EC2
│   ├── sync-repos-to-s3.py   # Sync code to KB bucket
│   └── create-opensearch-index.py
└── data/                     # Sample data
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| AI Agent | Strands SDK |
| LLM | Claude Sonnet 4 (Bedrock) |
| Vector Store | OpenSearch Serverless |
| Knowledge Base | Amazon Bedrock KB |
| Frontend | Streamlit |
| Infrastructure | AWS CDK (JavaScript) |
| MCP Transport | Server-Sent Events (SSE) |

## Documentation

- [CLAUDE.md](./CLAUDE.md) - Project context for AI assistants
- [DEMO.md](./DEMO.md) - Demo walkthrough and architecture
