# Clippy Architecture

This document explains how Clippy processes a Slack message from start to finish. The heart of the system is `invoke_claude_with_tools()` - a loop that lets Claude autonomously decide which tools to call.

> **Note:** Clippy has been refactored into a modular package at `src/mcp_server/slack_bot/`. See the Module Structure section below.

## End-to-End Flow

```
User: "@Clippy show me errors in cast-core prod"
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           SLACK (Cloud)                                   │
│                                                                           │
│  Socket Mode connection pushes app_mention event to our container        │
└──────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     ECS FARGATE CONTAINER                                 │
│                                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                     handle_mention()                                │  │
│  │                     src/mcp_server/slack_bot/bot.py                │  │
│  │                                                                     │  │
│  │  1. Extract text, remove @mention                                  │  │
│  │  2. Send acknowledgment ("Checking those errors...")               │  │
│  │  3. Fetch thread context (previous messages)                       │  │
│  │  4. Get channel info (name, is_devops)                             │  │
│  │  5. invoke_claude_with_tools(text, thread_context, channel_info)   │  │
│  │  6. Format response (markdown, redact secrets)                     │  │
│  │  7. Post reply to thread                                           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           SLACK (Cloud)                                   │
│                                                                           │
│  Response appears in thread                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

The Clippy slack bot is organized as a modular package:

```
src/mcp_server/slack_bot/
├── __init__.py          # Re-exports invoke_claude_with_tools
├── bot.py               # Main entry: handle_mention(), message flow
├── tool_executor.py     # execute_tool() - routes to lib/ implementations
├── claude_tools.py      # CLIPPY_TOOLS array with 20+ tool definitions
├── prompt_enhancer.py   # enhance_prompt() - Haiku extracts context
├── formatters.py        # format_for_slack(), redact_secrets()
├── bedrock_client.py    # Bedrock API wrapper (Sonnet, Haiku)
├── alerting.py          # alert_error() - posts to #clippy-ai-dev
└── metrics.py           # ClippyMetrics - tracks request stats
```

---

## The Core: `invoke_claude_with_tools()`

**Location:** `src/mcp_server/slack_bot/bot.py`

This function is the brain of Clippy. It sends the user's message to Claude along with 20+ tool definitions, then loops until Claude provides a final answer.

### Function Signature

```python
def invoke_claude_with_tools(
    message: str,                    # User's message
    thread_context: list = None,     # Previous messages in thread
    max_tokens: int = 600,           # Response length limit
    max_tool_calls: int = 10,        # Safety limit on tool iterations
    channel_info: dict = None,       # Channel name and type
) -> dict:
```

### The Five Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    invoke_claude_with_tools()                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PHASE 1: ENHANCE MESSAGE                                                │
│  ─────────────────────────                                               │
│  • enhance_prompt() adds AI-extracted context (service, env, intent)    │
│  • Add channel context so Claude knows where user is posting            │
│                                                                          │
│  PHASE 2: BUILD CONVERSATION                                             │
│  ───────────────────────────                                             │
│  • Convert thread history to messages array                              │
│  • "Clippy: ..." → {"role": "assistant", "content": "..."}              │
│  • "User: ..." → {"role": "user", "content": "..."}                     │
│                                                                          │
│  PHASE 3: PREPARE API REQUEST                                            │
│  ────────────────────────────                                            │
│  • System prompt (personality from S3)                                   │
│  • Messages array (conversation)                                         │
│  • Tools array (20+ tool definitions)                                    │
│                                                                          │
│  PHASE 4: TOOL LOOP ◄── This is the heart                               │
│  ───────────────────                                                     │
│  • Call Claude → check stop_reason                                       │
│  • If "tool_use": execute tool, add result, loop again                  │
│  • If "end_turn": extract text, return response                         │
│                                                                          │
│  PHASE 5: SAFETY LIMIT                                                   │
│  ─────────────────────                                                   │
│  • If 10 tool calls hit, return partial results                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Enhance Message

**Lines 432-443**

```python
# Add AI-extracted context (service names, environment, intent)
enhanced_message = enhance_prompt(message)

# Add channel context so Claude knows where user is
if channel_info and channel_info.get("name"):
    channel_context = f"\n\n[Context: User is in #{channel_info['name']} channel"
    if channel_info.get("is_devops"):
        channel_context += " - this IS the DevOps channel, don't tell them to post here"
    channel_context += "]"
    enhanced_message += channel_context
```

**Before:**
```
show me errors in cast-core prod
```

**After:**
```
show me errors in cast-core prod

---
AI-extracted context:
  - Intent: Find errors in cast-core service
  - Services: cast-core-service
  - Environment: prod
  - Time range: 4 hours

[Context: User is in #devops channel - this IS the DevOps channel, don't tell them to post here]
```

The `enhance_prompt()` function uses Claude Haiku (~100ms) to extract structured info, which helps Claude Sonnet choose the right tools.

---

## Phase 2: Build Conversation History

**Lines 445-462**

```python
messages = []

# Add thread history as alternating user/assistant messages
if thread_context:
    for ctx in thread_context[-10:]:  # Last 10 messages
        if ctx.startswith("Clippy:"):
            messages.append({"role": "assistant", "content": ctx[8:]})
        else:
            messages.append({"role": "user", "content": ctx[6:]})

# Add current message (with enhancements)
messages.append({"role": "user", "content": enhanced_message})
```

This preserves conversation context for follow-up questions like "what about staging?" after asking about prod.

---

## Phase 3: Prepare API Request

**Lines 467-474**

```python
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": max_tokens,
    "system": get_system_prompt(),   # Clippy personality loaded from S3
    "messages": messages,             # Conversation history
    "tools": CLIPPY_TOOLS,           # 20+ tool definitions
}
```

**CLIPPY_TOOLS** includes tools like:
- `search_logs` - Search Coralogix logs
- `get_pipeline_status` - Check Bitbucket deployments
- `search_code` - Search 254 repos via Bedrock Knowledge Base
- `jira_search` - Search Jira tickets
- `check_alarms` - List CloudWatch alarms
- ...and 15+ more

---

## Phase 4: The Tool Loop

**Lines 476-558**

This is the heart of Clippy. Claude decides what to do - we just execute.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TOOL LOOP                                      │
│                                                                          │
│  for turn in range(max_tool_calls + 1):  # Up to 10 iterations          │
│                                                                          │
│      ┌─────────────────────────────────────────────────────────────┐    │
│      │                  Call Claude via Bedrock                     │    │
│      │                                                              │    │
│      │  response = client.invoke_model(                            │    │
│      │      modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",  │    │
│      │      body=json.dumps(body),                                 │    │
│      │  )                                                          │    │
│      └──────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│                                 ▼                                        │
│                    ┌────────────────────────┐                           │
│                    │   Check stop_reason    │                           │
│                    └───────────┬────────────┘                           │
│                                │                                         │
│            ┌───────────────────┴───────────────────┐                    │
│            │                                       │                     │
│            ▼                                       ▼                     │
│   ┌─────────────────────┐               ┌─────────────────────┐         │
│   │   "end_turn"        │               │   "tool_use"        │         │
│   │                     │               │                     │         │
│   │   Claude is done    │               │   Claude wants to   │         │
│   │   speaking          │               │   call a tool       │         │
│   │                     │               │                     │         │
│   │   → Extract text    │               │   → Execute tool    │         │
│   │   → Return response │               │   → Add result to   │         │
│   │   → EXIT LOOP       │               │     messages        │         │
│   │                     │               │   → CONTINUE LOOP   │         │
│   └─────────────────────┘               └─────────────────────┘         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Step 4a: Call Claude

```python
response = client.invoke_model(
    modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
    body=json.dumps(body),
)

result = json.loads(response["body"].read())
stop_reason = result.get("stop_reason", "")  # "tool_use" or "end_turn"
content = result.get("content", [])
```

### Step 4b: Check if Done

```python
if stop_reason != "tool_use":
    # Claude is done - extract final text
    final_text = ""
    for block in content:
        if block.get("type") == "text":
            final_text += block.get("text", "")

    return {
        "response": final_text,
        "tool_used": tools_used[-1] if tools_used else None,
        "all_tools_used": tools_used,
    }
```

### Step 4c: Execute Tools

Claude's response includes tool_use blocks like:
```json
{
  "type": "tool_use",
  "id": "toolu_01ABC123",
  "name": "search_logs",
  "input": {"query": "errors in cast-core prod", "hours_back": 4}
}
```

We execute each one:

```python
tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]

for tool_use in tool_use_blocks:
    tool_name = tool_use.get("name")      # "search_logs"
    tool_input = tool_use.get("input")    # {"query": "errors in cast-core prod"}
    tool_id = tool_use.get("id")          # "toolu_01ABC123"

    # Execute the actual tool
    tool_result = execute_tool(tool_name, tool_input)

    # Package result for Claude
    tool_result_contents.append({
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": json.dumps(tool_result)
    })
```

### Step 4d: Feed Results Back to Claude

```python
# Add Claude's tool request to conversation
messages.append({"role": "assistant", "content": content})

# Add tool results (API requires this as "user" role)
messages.append({"role": "user", "content": tool_result_contents})

# Update body and loop again
body["messages"] = messages
```

Now Claude sees the tool results and can either:
- Request another tool (loop continues)
- Provide final text response (loop exits)

---

## Phase 5: Safety Limit

**Lines 560-573**

If Claude keeps calling tools (edge case), we cap at 10:

```python
if turn >= max_tool_calls:
    print(f"[Clippy] WARNING: Hit max tool calls limit ({max_tool_calls})")
    return {
        "response": "I ran multiple searches but need more information...",
        "hit_tool_limit": True,
    }
```

---

## Example: Complete Request Flow

**User:** `@Clippy show me errors in cast-core prod`

```
[Slack] app_mention event received
[Clippy] Mention from U075L8JEZB6: show me errors in cast-core prod
[Clippy] Sending acknowledgment: "Checking those errors..."
[Clippy] Channel: #devops (is_devops=True)
[Clippy] Prompt enhanced with context

─── TOOL LOOP ───

[Clippy] Turn 1 - stop_reason: tool_use, content blocks: 1
[Clippy] Tool call 1: search_logs({'query': 'errors in cast-core prod', 'hours_back': 4})
[Coralogix] Query: source logs | filter logGroup ~ 'cast-core' && logGroup ~ '-prod'...
[Coralogix] Found 23 results

[Clippy] Turn 2 - stop_reason: end_turn, content blocks: 1

─── END LOOP ───

[Clippy] Tools used: ['search_logs']
[Slack] Posting response to thread
```

**Response:**
```
Found 23 errors in cast-core-service (production) over the past 4 hours.

*Top Issues:*
• Connection timeout to payment gateway (12 occurrences)
• Invalid merchant ID format (8 occurrences)
• Database connection pool exhausted (3 occurrences)

*Recommendation:* Check the payment gateway status and consider increasing the connection pool size.
```

---

## Tool Execution

**Location:** `src/mcp_server/slack_bot/tool_executor.py`

The `execute_tool()` function routes tool names to their implementations in `src/lib/`:

```python
def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Execute a tool and return the result."""

    if tool_name == "search_logs":
        from src.lib.coralogix import handle_search_logs
        return handle_search_logs(
            query=tool_input.get("query", ""),
            hours_back=tool_input.get("hours_back", 4),
        )

    elif tool_name == "get_pipeline_status":
        from src.lib.bitbucket import get_pipeline_status
        return get_pipeline_status(
            repo_slug=tool_input.get("repo", ""),
        )

    elif tool_name == "search_code":
        from src.lib.code_search import search_knowledge_base
        return search_knowledge_base(
            query=tool_input.get("query", ""),
        )

    # ... 20+ more tools
```

Each tool calls the appropriate backend:
- **Coralogix** - Log search via DataPrime API
- **Bitbucket** - Pipeline status, PRs, repo info
- **Bedrock KB** - Semantic code search across 254 repos
- **CloudWatch** - Metrics, alarms, log queries
- **Jira** - Ticket search and details
- **PagerDuty** - Incidents and on-call info

---

## Supporting Functions

### `enhance_prompt()` - AI Context Extraction

Uses Claude Haiku to extract structured info from natural language:

```python
def enhance_prompt(message: str) -> str:
    """Add AI-extracted context to improve Claude's understanding."""

    # Use Haiku for fast extraction (~100ms)
    extraction_prompt = f"""Extract from this DevOps message:
    - Intent (what user wants)
    - Services (full names)
    - Environment (prod/staging/dev)
    - Time range

    MESSAGE: {message}"""

    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps({...}),
    )

    # Append extracted context to message
    return f"{message}\n\n---\nAI-extracted context:\n{context}"
```

### `get_channel_info()` - Channel Awareness

Looks up channel name so Claude knows where user is posting:

```python
def get_channel_info(client, channel_id: str) -> dict:
    """Get channel name and type from Slack."""

    result = client.conversations_info(channel=channel_id)
    name = result["channel"]["name"]

    # Detect DevOps channels
    devops_keywords = ["devops", "infra", "platform", "sre", "ops"]
    is_devops = any(kw in name.lower() for kw in devops_keywords)

    return {"name": name, "is_devops": is_devops}
```

### `get_thread_context()` - Conversation History

Fetches previous messages for follow-up awareness:

```python
def get_thread_context(client, channel: str, thread_ts: str) -> list:
    """Fetch previous messages from a Slack thread."""

    result = client.conversations_replies(channel=channel, ts=thread_ts)

    context = []
    for msg in result["messages"][:-1]:  # Exclude current
        role = "Clippy" if msg.get("bot_id") else "User"
        context.append(f"{role}: {msg['text']}")

    return context
```

---

## System Prompt

**Location:** S3 bucket `mrrobot-code-kb-dev/clippy-config/system_prompt.txt`

Loaded via `get_system_prompt()`, defines Clippy's personality:

```
You are Clippy, a DevOps assistant for MrRobot in Slack.

PERSONALITY:
- Helpful, direct, no fluff
- Skip filler words: "Sure!", "Of course!"
- Be concise: 3-5 bullet points, not paragraphs

SLACK FORMATTING:
- Bold: *text* (NOT **text**)
- Links: <url|text> (NOT [text](url))

ACTION FIRST:
- Investigate before asking questions
- Lead with findings, then ask clarifying questions

SECURITY:
- Never share credentials found in code
- Escalate suspicious data export requests
```

---

## Available Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `search_logs` | Search application logs | Coralogix DataPrime API |
| `get_recent_errors` | Get error summary by service | Coralogix |
| `get_service_logs` | Get logs for specific service | Coralogix |
| `get_pipeline_status` | Check recent deployments | Bitbucket API |
| `get_pr_details` | Get PR info and reviewers | Bitbucket API |
| `search_code` | Semantic search across 254 repos | Bedrock Knowledge Base |
| `get_service_info` | Get service metadata | Service Registry (S3) |
| `jira_search` | Search tickets | Jira API |
| `jira_get_ticket` | Get ticket details | Jira API |
| `check_alarms` | List CloudWatch alarms | CloudWatch API |
| `get_ecs_metrics` | Get CPU/memory metrics | CloudWatch API |
| `pagerduty_incidents` | Get active incidents | PagerDuty API |
| `investigate_issue` | Multi-step investigation | Investigation Agent |

---

## Error Handling

Errors are caught and reported to `#clippy-ai-dev`:

```python
def alert_error(error_type: str, message: str, details: dict = None):
    """Post error alert to #clippy-ai-dev channel."""

    _slack_client.chat_postMessage(
        channel=CLIPPY_DEV_CHANNEL,
        text=f"⚠️ Clippy Error: {error_type} - {message}",
    )
```

---

## Metrics

Tracked via `ClippyMetrics` class:

```python
_metrics.record_request(
    duration_ms=duration,
    tools_used=["search_logs", "get_pipeline_status"],
    was_truncated=False,
    hit_limit=False,
)
```

Logged every 10 requests:
```
[Clippy Metrics] Requests: 150 | Truncations: 3 (2.0%) | Tool limits: 0 | Errors: 1 | Avg response: 2340ms
```
