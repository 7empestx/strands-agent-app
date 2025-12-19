# CLAUDE.md - Project Context for AI Assistants

## Project Overview

**Strands Agent App** is a DevOps AI assistant platform with:
1. **Streamlit UI** - Web interface for merchant insights and code search
2. **MCP Server** - Remote Model Context Protocol server for AI IDE integration
3. **Bedrock Knowledge Base** - Vector search over 254 MrRobot repositories (17,169 documents)

## Infrastructure

| Resource | Value |
|----------|-------|
| EC2 Instance | `i-089292d2c5a6a055f` |
| Elastic IP | `34.202.219.55` |
| Knowledge Base ID | `SAJJWYFTNG` |
| Data Source ID | `QZIIJTGQAR` |
| S3 Bucket | `mrrobot-code-kb-dev-720154970215` |
| OpenSearch Endpoint | `https://12rasdapmp78icp6swwa.us-east-1.aoss.amazonaws.com` |
| AWS Account | `720154970215` (dev) |
| Region | `us-east-1` |

## Services Running on EC2

| Service | Port | URL | DNS |
|---------|------|-----|-----|
| MCP Server | 8080 | `http://34.202.219.55:8080/sse` | `https://mcp.mrrobot.dev/sse` |
| Streamlit | 8501 | `http://34.202.219.55:8501` | `http://ai-agent.mrrobot.dev:8501` |

## MCP Server for AI IDEs

The MCP server provides code search capabilities via Bedrock Knowledge Base. It's accessible to Cursor, Claude Code, and other MCP-compatible tools.

### Cursor Configuration

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

### Claude Code Configuration

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

**Requirement:** Must be connected to VPN to access the MCP server.

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `search_code` | Search MrRobot codebase using natural language queries |

Example queries:
- "How does authentication work in the API?"
- "Find Lambda functions that process payments"
- "Show me database connection patterns"

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

## Common Commands

### Deploy to EC2

```bash
# Deploy code only
./scripts/deploy-to-ec2.sh

# Deploy and restart services
./scripts/deploy-to-ec2.sh --start
```

### Deploy Infrastructure

```bash
cd infra

# EC2 stack
AWS_PROFILE=dev npx cdk deploy StrandsAgentStack

# Knowledge Base stack (two phases)
SKIP_KB=true AWS_PROFILE=dev npx cdk deploy CodeKnowledgeBaseStack
# Wait 10 min, then create index
AWS_PROFILE=dev python scripts/create-opensearch-index.py --endpoint <endpoint>
# Final deploy
AWS_PROFILE=dev npx cdk deploy CodeKnowledgeBaseStack
```

### SSH to EC2

```bash
ssh -i ~/.ssh/streamlit-key.pem ec2-user@34.202.219.55
```

### Check Services on EC2

```bash
ssh -i ~/.ssh/streamlit-key.pem ec2-user@34.202.219.55 \
  "sudo systemctl status mcp-server streamlit"
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
| Hosting | EC2 with Elastic IP |
