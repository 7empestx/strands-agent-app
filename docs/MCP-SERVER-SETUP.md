# MrRobot Code Knowledge Base - MCP Server Setup Guide

> **Last Updated:** December 2024 (Tools updated)
> **Status:** Production Ready
> **Access:** VPN Required

## Overview

We've deployed an MCP (Model Context Protocol) server that provides AI-powered code search across all MrRobot repositories. This enables your AI coding assistant (Cursor, Claude Code, etc.) to search and understand our codebase.

### What's Included

- **254 repositories** from Bitbucket
- **17,169 documents** indexed
- Semantic search powered by **Amazon Bedrock Knowledge Base**
- Real-time access via **Server-Sent Events (SSE)**

## Quick Setup

### Prerequisites

1. **VPN Connection** - Must be connected to access the server
2. **AI IDE** - Cursor, Claude Code, or any MCP-compatible tool

### Cursor Setup

1. Open or create the file `~/.cursor/mcp.json`
2. Add the following configuration:

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

3. Restart Cursor
4. The "mrrobot-code-kb" server should appear in your MCP panel

### Claude Code Setup

1. Open or create the file `~/.claude/settings.json`
2. Add the following configuration:

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

3. Restart Claude Code
4. The MCP tools will be available in your session

### Other MCP-Compatible Tools

Use these connection details:
- **URL:** `https://mcp.mrrobot.dev/sse`
- **Transport:** SSE (Server-Sent Events)

## How to Use

Once connected, you can ask your AI assistant questions about the MrRobot codebase:

### Example Queries

| Query | What it does |
|-------|--------------|
| "How does authentication work in the payment API?" | Searches for auth patterns |
| "Find Lambda functions that process settlements" | Locates serverless code |
| "Show me database connection patterns" | Finds DB config examples |
| "What error handling patterns exist?" | Discovers error handling |
| "Find webhook implementations" | Locates webhook handlers |

### Tips for Better Results

1. **Be specific** - "Find JWT validation in the gateway" is better than "authentication code"
2. **Mention technologies** - "Lambda", "DynamoDB", "Node.js", etc.
3. **Include context** - "in the settlement service" narrows the search

## Available Tools

The MCP server provides 30+ tools across multiple categories:

### Code Search (Bedrock Knowledge Base)
| Tool | Description |
|------|-------------|
| `search_mrrobot_repos` | Semantic search across all 254 repos |
| `search_in_repo` | Search within a specific repository |
| `find_similar_code` | Find similar code patterns |
| `get_file_content` | Fetch full file content from Bitbucket |
| `search_by_file_type` | Search specific file types (e.g., `*.py`, `*.ts`) |

### Coralogix (Log Analysis)
| Tool | Description |
|------|-------------|
| `coralogix_search_logs` | Natural language log search (auto-converts to DataPrime) |
| `coralogix_get_recent_errors` | Get errors grouped by service |
| `coralogix_get_service_logs` | Logs for a specific service |
| `coralogix_get_service_health` | Health overview for services |

### Bitbucket
| Tool | Description |
|------|-------------|
| `bitbucket_list_prs` | List pull requests (open/merged/declined) |
| `bitbucket_pipeline_status` | Get recent pipeline/deploy status |
| `bitbucket_get_pr_details` | Get PR diff, comments, reviewers |
| `bitbucket_get_repo_info` | Repository metadata |
| `bitbucket_list_branches` | List branches in a repo |
| `bitbucket_get_commits` | Recent commits |

### Atlassian Admin
| Tool | Description |
|------|-------------|
| `atlassian_list_users` | List users in organization |
| `atlassian_search_users` | Search users by email/name |
| `atlassian_list_groups` | List groups |
| `atlassian_get_user_groups` | Get groups for a user |
| `atlassian_add_user_to_group` | Add user to group |
| `atlassian_remove_user_from_group` | Remove user from group |

### AWS CLI (Read-Only)
| Tool | Description |
|------|-------------|
| `aws_cli_command` | Run allowlisted read-only AWS commands |

Blocked commands: `delete`, `terminate`, `create`, `put`, `get-secret-value`

## Troubleshooting

### "Connection Failed"

1. Verify VPN is connected
2. Test the endpoint: `curl https://mcp.mrrobot.dev/sse`
3. Check if you can reach `mcp.mrrobot.dev` from your network

### "No Results Found"

1. Try broader search terms
2. Check if the code exists in a repository synced to the KB
3. Try rephrasing the query

### "Server Unavailable"

1. The ECS service may be restarting
2. Contact DevOps to check service status

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Your IDE      │────▶│   MCP Server    │────▶│  Bedrock KB     │
│ (Cursor/Claude) │ SSE │  (ECS Fargate)  │     │  (SAJJWYFTNG)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │   OpenSearch    │
                                                │   Serverless    │
                                                └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │   S3 Bucket     │
                                                │ (254 repos)     │
                                                └─────────────────┘
```

## Infrastructure Details

| Component | Value |
|-----------|-------|
| MCP Server URL | `https://mcp.mrrobot.dev/sse` |
| ECS Cluster | `mrrobot-ai-core` |
| Knowledge Base ID | `SAJJWYFTNG` |
| AWS Region | `us-east-1` |
| Embedding Model | `amazon.titan-embed-text-v2:0` |

## Support

- **Slack:** #devops-ai-tools
- **Documentation:** See CLAUDE.md in the mrrobot-ai-core repo
- **Issues:** Contact DevOps team

## Changelog

- **Dec 2024** - Initial deployment with 254 repositories
