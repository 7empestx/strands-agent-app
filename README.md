# Strands Agent App

AI-powered platform for merchant insights and code search using **Strands SDK** + **Claude Sonnet on Amazon Bedrock**.

## Features

### 1. Merchant Insights Agent (Streamlit)
Natural language interface for merchants to understand their payment data:
- "Give me an overview of my transactions"
- "Why are cards being declined?"
- "When will I get my next deposit?"

### 2. Code Knowledge Base (MCP Server)
Search 254 MrRobot repositories (17,169 documents) via AI-powered semantic search:
- Integrated with Cursor, Claude Code, and other MCP-compatible IDEs
- Natural language queries: "How does authentication work in the API?"
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
├── app.py                  # Streamlit frontend
├── agent.py                # Merchant insights agent
├── mcp-servers/
│   └── bedrock-kb-server.py  # MCP server for KB search
├── infra/                  # AWS CDK (JavaScript)
│   ├── bin/app.js
│   └── lib/
│       ├── strands-agent-stack.js    # EC2 infrastructure
│       ├── knowledge-base-stack.js   # Bedrock KB infrastructure
│       └── constants/
│           └── aws-accounts.js       # Shared AWS config
├── scripts/
│   ├── deploy-to-ec2.sh    # Deploy app to EC2
│   ├── sync-repos-to-s3.py # Sync code to KB bucket
│   └── create-opensearch-index.py
└── data/                   # Sample merchant data
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
