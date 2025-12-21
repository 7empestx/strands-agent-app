# CLAUDE.md - Project Context for AI Assistants

## Project Overview

**Strands Agent App** is a DevOps AI assistant platform with:
1. **Slack Bot (Clippy)** - AI assistant in #devops channel for logs, pipelines, PRs, AWS queries
2. **MCP Server** - 30+ tools for AI IDEs (Cursor, Claude Code)
3. **Streamlit Dashboard** - Web UI with specialized AI agents
4. **Bedrock Knowledge Base** - Vector search over 254 MrRobot repositories (17,169 documents)

## Architecture

```
src/
├── mcp_server/           # Entry: server.py --http --port 8080 --slack
│   ├── server.py         # FastMCP server with 30+ tools
│   └── slack_bot.py      # Clippy - Claude Tool Use architecture
├── streamlit/            # Entry: streamlit run app.py
│   ├── app.py            # Main dashboard
│   └── *_agent.py        # Strands agents (wrap lib/ functions)
└── lib/                  # Shared handlers (framework-agnostic)
    ├── coralogix.py      # Log search, DataPrime queries
    ├── bitbucket.py      # PRs, pipelines, repos
    ├── cloudwatch.py     # Metrics, alarms, logs
    ├── code_search.py    # Bedrock KB search
    ├── atlassian.py      # User/group management
    ├── aws_cli.py        # Safe read-only AWS CLI wrapper
    └── utils/            # AWS clients, config, secrets
```

**Key Pattern:** `lib/` contains raw API functions. `streamlit/*_agent.py` wraps them with Strands `@tool` decorators. `mcp_server/server.py` wraps them with FastMCP `@mcp.tool()` decorators.

## Infrastructure

| Resource | Value |
|----------|-------|
| ECS Cluster | `mrrobot-ai-core` |
| MCP Server | `https://mcp.mrrobot.dev/sse` |
| Streamlit | `https://ai-agent.mrrobot.dev` |
| Knowledge Base ID | `SAJJWYFTNG` |
| AWS Account | `720154970215` (dev) |
| Region | `us-east-1` |

## Slack Bot (Clippy)

Located at `src/mcp_server/slack_bot.py`. Uses **Claude Tool Use** architecture:
- User message → Claude with tool definitions
- Claude decides which tools to call (can call multiple in parallel)
- Tools execute → Claude summarizes results
- No hardcoded intent classification

**Key Features:**
- Responds once per thread (avoids spam)
- AI-generated acknowledgment messages
- Secret redaction in responses
- Slack formatting (`*bold*` not `**bold**`)
- 600 token max for concise responses

**Available Tools:**
- `search_logs` - Coralogix log search
- `get_recent_errors` - Error summary by service
- `get_pipeline_status` - Bitbucket pipeline status
- `get_pipeline_details` - Failure reasons from logs
- `get_open_prs` / `get_pr_details` - PR information
- `run_aws_command` - Read-only AWS CLI (allowlisted)
- `list_alarms` - CloudWatch alarms
- `search_code` - Bedrock KB search
- `investigate_issue` - Multi-step investigation agent

## MCP Tools

### Code Search (Bedrock Knowledge Base)
| Tool | Description |
|------|-------------|
| `search_mrrobot_repos` | Semantic search across all 254 repos |
| `search_in_repo` | Search within a specific repository |
| `find_similar_code` | Find similar code patterns |
| `get_file_content` | Fetch full file from Bitbucket |
| `search_by_file_type` | Search specific file types |

### Coralogix (Log Analysis)
| Tool | Description |
|------|-------------|
| `coralogix_search_logs` | Natural language → DataPrime query |
| `coralogix_get_recent_errors` | Errors grouped by service |
| `coralogix_get_service_logs` | Logs for specific service |
| `coralogix_get_service_health` | Health overview |

### Bitbucket
| Tool | Description |
|------|-------------|
| `bitbucket_list_prs` | List pull requests |
| `bitbucket_pipeline_status` | CI/CD pipeline status |
| `bitbucket_get_pr_details` | PR diff and comments |

### CloudWatch
| Tool | Description |
|------|-------------|
| `cloudwatch_list_alarms` | List alarms by state |
| `cloudwatch_query_logs` | CloudWatch Logs Insights |
| `cloudwatch_ecs_metrics` | ECS CPU/memory metrics |

### AWS CLI (Read-Only)
Allowlisted commands only. Blocked: delete, terminate, create, get-secret-value.

## Common Commands

### Deploy to ECS
```bash
./scripts/deploy-to-ecs.sh
```

### View Logs
```bash
# MCP Server + Slack Bot
AWS_PROFILE=dev aws logs tail /ecs/mrrobot-mcp-server --follow --region us-east-1

# Streamlit
AWS_PROFILE=dev aws logs tail /ecs/mrrobot-streamlit --follow --region us-east-1
```

### Test Slack Bot Locally
```bash
python tests/clippy_test_prompts.py -i  # Interactive mode
python tests/clippy_test_prompts.py -s  # Run all prompts
```

### Deploy Infrastructure
```bash
cd infra
AWS_PROFILE=dev npx cdk deploy StrandsAgentECSStack
AWS_PROFILE=dev npx cdk deploy CodeKnowledgeBaseStack
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

## File Locations

| What | Where |
|------|-------|
| Slack bot | `src/mcp_server/slack_bot.py` |
| MCP server | `src/mcp_server/server.py` |
| Streamlit app | `src/streamlit/app.py` |
| Coralogix handlers | `src/lib/coralogix.py` |
| Bitbucket handlers | `src/lib/bitbucket.py` |
| AWS CLI wrapper | `src/lib/aws_cli.py` |
| KB search | `src/lib/code_search.py` |
| ECS infrastructure | `infra/lib/ecs-fargate-stack.js` |
| Deploy script | `scripts/deploy-to-ecs.sh` |
