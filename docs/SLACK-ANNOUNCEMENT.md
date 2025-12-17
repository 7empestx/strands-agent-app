# Slack Announcement - MrRobot Code Knowledge Base MCP Server

## Short Version (for #engineering)

---

**New: AI-Powered Code Search for Your IDE**

We've deployed an MCP server that lets you search our entire codebase (254 repos, 17K+ files) from Cursor, Claude Code, or any MCP-compatible tool.

**Quick Setup (Cursor):**
1. Connect to VPN
2. Add to `~/.cursor/mcp.json`:
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
3. Restart Cursor

Then ask your AI: "How does authentication work?" or "Find payment processing Lambda functions"

Full setup guide: [link to Confluence]

---

## Detailed Version (for #devops or #tech-announcements)

---

**Introducing: MrRobot Code Knowledge Base - AI Code Search for Your IDE**

We've deployed an MCP (Model Context Protocol) server that provides AI-powered semantic search across our entire codebase. This means your AI coding assistant can now search and understand MrRobot code.

**What's Included:**
- 254 repositories from Bitbucket
- 17,169 documents indexed
- Powered by Amazon Bedrock Knowledge Base
- Real-time access via Server-Sent Events

**Supported Tools:**
- Cursor
- Claude Code
- Any MCP-compatible IDE

**Requirements:**
- VPN connection required

**Setup Instructions:**

For **Cursor**, add to `~/.cursor/mcp.json`:
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

For **Claude Code**, add to `~/.claude/settings.json`:
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

**Example Queries:**
- "How does authentication work in the payment API?"
- "Find Lambda functions that process settlements"
- "Show me database connection patterns"
- "What error handling patterns exist in the codebase?"

**Documentation:** Full setup guide available in Confluence: [MCP Server Setup Guide]

**Questions?** Reach out in #devops-ai-tools

---

## Copy-Paste Ready (Slack formatting)

```
:rocket: *New: AI-Powered Code Search for Your IDE*

We've deployed an MCP server that lets you search our entire codebase (254 repos, 17K+ files) directly from Cursor, Claude Code, or any MCP-compatible tool.

*Quick Setup (Cursor):*
1. Connect to VPN
2. Add to `~/.cursor/mcp.json`:
```
{
  "mcpServers": {
    "mrrobot-code-kb": {
      "url": "http://mcp.mrrobot.dev:8080/sse",
      "transport": "sse"
    }
  }
}
```
3. Restart Cursor

*Example queries:*
• "How does authentication work in the API?"
• "Find Lambda functions that process payments"
• "Show me database connection patterns"

:page_facing_up: Full setup guide: <link to Confluence|MCP Server Setup Guide>
:question: Questions? Ask in #devops-ai-tools
```
