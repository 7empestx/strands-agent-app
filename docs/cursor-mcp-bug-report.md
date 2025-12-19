# Bug Report: Remote MCP Server Shows "Error" on Startup Despite Successful Connection

## Environment
- **Cursor Version**: Latest (December 2024)
- **OS**: macOS
- **MCP Transport**: StreamableHTTP (also tested with SSE)
- **Server**: Remote MCP server on AWS ECS (responds in ~150ms)

## Description

When opening Cursor, remote MCP servers intermittently show "Error" status even though the server is healthy and responding correctly. Toggling the server off/on in settings immediately fixes it.

## Steps to Reproduce

1. Configure a remote MCP server in `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "my-server": {
      "url": "http://mcp.example.com/sse",
      "transport": "sse"
    }
  }
}
```
2. Quit Cursor completely
3. Open Cursor
4. Go to Settings → Tools & MCP
5. Observe server shows red dot with "Error - Show Output"
6. Toggle server off, then on
7. Server immediately shows green (working)

## Expected Behavior

Server should connect successfully on Cursor startup without requiring manual toggle.

## Actual Behavior

Server shows "Error" on startup, but works immediately after toggling.

## Evidence Server Is Healthy

**Health check (instant response):**
```bash
$ curl -s http://mcp.example.com/health
{"status":"ok","transport":"streamable-http+sse"}
```

**StreamableHTTP test (150ms response):**
```bash
$ curl -X POST http://mcp.example.com/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
{"id":1,"jsonrpc":"2.0","result":{"tools":[...]}}  # Returns 7 tools
```

## MCP Output Logs (After Toggle - Working)

```
2024-12-17 23:05:24.540 [info] Creating streamableHttp transport
2024-12-17 23:05:24.540 [info] Connecting to streamableHttp server
2024-12-17 23:05:24.927 [info] Successfully connected to streamableHttp server
2024-12-17 23:05:25.087 [info] listOfferings: Found 7 tools
```

## Analysis

The connection succeeds in <400ms after toggle, suggesting the issue is:

1. **Startup race condition** - Cursor marks error before connection completes
2. **Aggressive timeout** - Remote servers need slightly more time than local
3. **Missing retry logic** - First failure should trigger automatic retry

## Workaround

Toggle server off/on in Settings → Tools & MCP

## Related Issues

- #3640 - Invalid session ID after reconnect
- #3722 - Token expiration handling
- #3734 - OAuth flow issues

## Suggested Fix

Add retry logic with exponential backoff for remote MCP servers:

```typescript
async connectWithRetry(maxRetries = 3, baseDelay = 500) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      await this.connect();
      return;
    } catch (e) {
      if (i < maxRetries - 1) {
        await sleep(baseDelay * Math.pow(2, i));
      }
    }
  }
  this.markError();
}
```

---

**Post to**: https://github.com/getcursor/cursor/issues/new

**Labels**: `bug`, `mcp`, `remote-server`

