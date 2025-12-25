# AI Improvement Plan for Clippy

This document outlines improvements to enhance Clippy's AI capabilities, response quality, and user experience.

## Current Architecture

Clippy uses a **Claude Tool Use** architecture:
1. **Prompt Enhancement** (`prompt_enhancer.py`) - Uses Claude Haiku to extract context (service, environment, intent, urgency, entities)
2. **Tool Use Loop** (`claude_tools.py`) - Claude Sonnet decides which tools to call, executes them, loops until done
3. **Tool Execution** (`tool_executor.py`) - Routes tool calls to `src/lib/` implementations
4. **Response Formatting** (`formatters.py`) - Converts to Slack markdown, redacts secrets

**Current LLM Usage:**
- Claude Haiku (3.0) - Prompt enhancement (fast, cheap)
- Claude Sonnet 4 - Main reasoning and tool orchestration

---

## Phase 1: Quick Wins (1-2 days)

### 1.1 Improve System Prompt

**Location:** `s3://mrrobot-code-kb-dev-720154970215/clippy-config/system_prompt.txt`

**Current Issues:**
- Generic DevOps assistant prompt
- No explicit guidance on error investigation workflow
- Missing examples of multi-tool usage patterns

**Improvements:**
```text
# Add investigation workflow guidance
When investigating errors:
1. ALWAYS check logs first (search_logs with service + env)
2. Check recent deploys (get_pipeline_status) if timing correlates
3. Search code (search_code) if error message suggests config/code issue
4. Check PagerDuty (pagerduty_active_incidents) if multiple services affected

# Add response formatting guidance
- Lead with the answer/finding
- Include relevant timestamps
- Show specific error messages when found
- Suggest next steps if issue not resolved
```

### 1.2 Add Few-Shot Examples to Tools

**Location:** `src/mcp_server/clippy_tools.py`

Add examples to tool descriptions showing when/how to use them:

```python
_tool(
    name="search_logs",
    description="""Search application logs in Coralogix.

Examples:
- "errors in cast-core prod" → searches prod cast-core for errors
- "timeout issues in staging" → searches staging for timeouts
- "504 gateway timeout emvio-dashboard" → searches for specific error

ALWAYS include environment (prod/staging/dev) when user specifies it.""",
    ...
)
```

### 1.3 Implement Feedback Collection

**File:** `src/mcp_server/slack_bot/bot.py`

Add reaction monitoring for response quality feedback:

```python
# After sending response
msg = say(response, thread_ts=thread_ts)

# Store message info for feedback tracking
store_message_for_feedback(
    message_ts=msg["ts"],
    user_query=text,
    tools_used=result.get("all_tools_used", []),
    response_preview=response[:200]
)

# In separate handler:
@app.event("reaction_added")
def handle_reaction(event, client):
    if event["reaction"] in ["thumbsup", "thumbsdown"]:
        log_feedback(event["item"]["ts"], event["reaction"])
```

---

## Phase 2: Enhanced Context & Memory (3-5 days)

### 2.1 Conversation Memory

**Current State:** Only uses thread context (last 10 messages)

**Improvement:** Add cross-thread memory for recurring issues

```python
# src/mcp_server/slack_bot/memory.py
class ConversationMemory:
    def __init__(self, s3_bucket, ttl_hours=24):
        self.bucket = s3_bucket
        self.ttl = ttl_hours

    def store_investigation(self, service, env, findings, timestamp):
        """Store investigation results for future reference."""
        key = f"memory/{service}/{env}/{timestamp}.json"
        # Store: error patterns, resolution, tools used

    def get_recent_investigations(self, service, env, hours=24):
        """Get recent investigations for context."""
        # Return recent findings to add to prompt context
```

**Usage in `invoke_claude_with_tools()`:**
```python
# Add to message context
recent = memory.get_recent_investigations(service, env)
if recent:
    enhanced_message += f"\n\n[Recent related investigation: {recent['summary']}]"
```

### 2.2 Smart Service Detection

**Current State:** Haiku extracts service names, but relies on hardcoded alias list

**Improvement:** Use service registry more effectively

```python
# src/mcp_server/slack_bot/prompt_enhancer.py

def enhance_prompt_with_ai(message: str) -> str:
    # Load full service registry
    registry = get_service_registry()

    # Build dynamic alias list (top 50 most common)
    service_context = build_service_context(registry, limit=50)

    extraction_prompt = f"""...
Known services (with aliases):
{service_context}
..."""
```

### 2.3 Error Pattern Learning

**New File:** `src/lib/error_patterns.py`

Store and match common error patterns:

```python
ERROR_PATTERNS = {
    "ECONNREFUSED": {
        "cause": "Service connection failure",
        "check": ["target service status", "network connectivity", "security groups"],
        "tools": ["search_logs", "aws_cli"]
    },
    "504 Gateway Timeout": {
        "cause": "Backend timeout",
        "check": ["lambda duration", "downstream services", "database performance"],
        "tools": ["search_logs", "get_pipeline_status"]
    },
    "CORS": {
        "cause": "Cross-origin request blocked",
        "check": ["API gateway config", "Lambda headers", "CloudFront behavior"],
        "tools": ["search_code", "search_logs"]
    }
}

def get_investigation_hints(error_message: str) -> dict:
    """Match error message to known patterns and return investigation hints."""
```

---

## Phase 3: Advanced Reasoning (5-7 days)

### 3.1 Multi-Step Investigation Agent

**Current State:** Claude decides tools ad-hoc, may miss investigation steps

**Improvement:** Structured investigation workflow

```python
# src/lib/investigation_workflow.py

class InvestigationWorkflow:
    """Structured multi-step investigation for production issues."""

    PHASES = [
        ("logs", "Check recent logs for errors"),
        ("deploys", "Check if recent deploys correlate"),
        ("metrics", "Check service health metrics"),  # via Coralogix
        ("incidents", "Check for related PagerDuty incidents"),
        ("code", "Search code if config/code issue suspected"),
        ("history", "Check if similar issue occurred before"),
    ]

    async def investigate(self, service, env, description):
        """Run structured investigation."""
        findings = {}

        for phase, desc in self.PHASES:
            result = await self._run_phase(phase, service, env, description)
            findings[phase] = result

            # Early exit if root cause found
            if result.get("root_cause_likely"):
                break

        return self._summarize_findings(findings)
```

### 3.2 Confidence Scoring

Add confidence scores to tool results:

```python
# src/mcp_server/slack_bot/tool_executor.py

def execute_tool(tool_name: str, tool_input: dict) -> dict:
    result = _execute_tool_internal(tool_name, tool_input)

    # Add confidence scoring
    result["confidence"] = calculate_confidence(tool_name, result)
    result["completeness"] = assess_completeness(result)

    return result

def calculate_confidence(tool_name: str, result: dict) -> float:
    """Score 0-1 based on result quality."""
    if "error" in result:
        return 0.0
    if tool_name == "search_logs":
        logs = result.get("logs", [])
        if len(logs) >= 10:
            return 0.9
        elif len(logs) > 0:
            return 0.7
        else:
            return 0.3  # Empty results - maybe wrong query
    # ... more tool-specific scoring
```

### 3.3 Self-Reflection Loop

Add a reflection step before final response:

```python
# In claude_tools.py invoke_claude_with_tools()

# Before returning final response, add reflection
if tools_used and final_text:
    reflection_prompt = f"""Review your investigation:

Tools used: {tools_used}
Findings: {final_text[:500]}

Questions to consider:
1. Did you check all relevant sources?
2. Is the root cause clear or should you investigate more?
3. Is there additional context that would help?

If investigation is incomplete, return "NEED_MORE: <what to check>"
If complete, return "COMPLETE: <summary>"
"""
    # Quick reflection call with Haiku
    reflection = call_haiku(reflection_prompt)
    if reflection.startswith("NEED_MORE:"):
        # Continue investigation
        ...
```

---

## Phase 4: Performance & Reliability (3-5 days)

### 4.1 Caching Layer

```python
# src/lib/utils/cache.py

class TTLCache:
    """In-memory cache with TTL for repeated queries."""

    def __init__(self, default_ttl=300):
        self.cache = {}
        self.ttl = default_ttl

    def get(self, key):
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            del self.cache[key]
        return None

    def set(self, key, value, ttl=None):
        ttl = ttl or self.ttl
        self.cache[key] = (value, time.time() + ttl)

# Usage in tool executor
cache = TTLCache(ttl=60)  # 1 min cache

def execute_tool(tool_name, tool_input):
    cache_key = f"{tool_name}:{hash(json.dumps(tool_input, sort_keys=True))}"
    cached = cache.get(cache_key)
    if cached:
        print(f"[Clippy] Cache hit for {tool_name}")
        return cached

    result = _execute_tool_internal(tool_name, tool_input)
    cache.set(cache_key, result)
    return result
```

### 4.2 Parallel Tool Execution

Claude already supports parallel tool calls. Ensure we execute them in parallel:

```python
# src/mcp_server/slack_bot/tool_executor.py

import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=5)

async def execute_tools_parallel(tool_calls: list) -> list:
    """Execute multiple tool calls in parallel."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(executor, execute_tool, call["name"], call["input"])
        for call in tool_calls
    ]
    return await asyncio.gather(*tasks)
```

### 4.3 Graceful Degradation

```python
# Handle API failures gracefully
def execute_tool(tool_name: str, tool_input: dict) -> dict:
    try:
        result = _execute_tool_internal(tool_name, tool_input)
    except Exception as e:
        # Return degraded result instead of error
        return {
            "partial": True,
            "error": str(e),
            "fallback_message": f"Could not fetch {tool_name} data. {get_fallback_suggestion(tool_name)}",
            "suggestion": get_alternative_tools(tool_name)
        }
```

---

## Phase 5: Observability & Learning (Ongoing)

### 5.1 Structured Logging

```python
# src/mcp_server/slack_bot/observability.py

import json
from datetime import datetime

def log_interaction(
    user_query: str,
    enhanced_query: str,
    tools_used: list,
    tool_results: dict,
    final_response: str,
    duration_ms: float,
    feedback: str = None
):
    """Log structured interaction data for analysis."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_query": user_query,
        "enhanced_query": enhanced_query,
        "tools_used": tools_used,
        "tool_result_sizes": {k: len(str(v)) for k, v in tool_results.items()},
        "response_length": len(final_response),
        "duration_ms": duration_ms,
        "feedback": feedback,
    }
    # Send to CloudWatch Logs or S3 for analysis
    print(f"[METRICS] {json.dumps(log_entry)}")
```

### 5.2 A/B Testing Framework

```python
# src/mcp_server/slack_bot/experiments.py

EXPERIMENTS = {
    "prompt_v2": {
        "enabled": True,
        "percentage": 50,  # 50% of requests
        "variant_a": "current_system_prompt",
        "variant_b": "new_system_prompt_with_examples",
    }
}

def get_experiment_variant(experiment_name: str, user_id: str) -> str:
    """Get consistent experiment variant for user."""
    exp = EXPERIMENTS.get(experiment_name)
    if not exp or not exp["enabled"]:
        return "control"

    # Consistent assignment based on user_id hash
    if hash(user_id) % 100 < exp["percentage"]:
        return "variant_b"
    return "variant_a"
```

---

## Implementation Priority

| Phase | Effort | Impact | Priority |
|-------|--------|--------|----------|
| 1.1 Improve System Prompt | Low | High | P0 |
| 1.2 Few-Shot Examples | Low | Medium | P0 |
| 1.3 Feedback Collection | Medium | High | P1 |
| 2.1 Conversation Memory | Medium | Medium | P2 |
| 2.2 Smart Service Detection | Low | Medium | P1 |
| 2.3 Error Pattern Learning | Medium | High | P1 |
| 3.1 Investigation Workflow | High | High | P2 |
| 3.2 Confidence Scoring | Medium | Medium | P2 |
| 3.3 Self-Reflection | Medium | Medium | P3 |
| 4.1 Caching Layer | Low | Medium | P1 |
| 4.2 Parallel Execution | Low | Low | P3 |
| 4.3 Graceful Degradation | Low | High | P1 |
| 5.1 Structured Logging | Low | Medium | P1 |
| 5.2 A/B Testing | Medium | High | P2 |

---

## Quick Start Implementation

To start improving Clippy AI immediately:

1. **Update system prompt** (no code change):
   ```bash
   aws s3 cp s3://mrrobot-code-kb-dev-720154970215/clippy-config/system_prompt.txt ./
   # Edit with investigation workflow guidance
   aws s3 cp ./system_prompt.txt s3://mrrobot-code-kb-dev-720154970215/clippy-config/
   ```

2. **Add few-shot examples** to `clippy_tools.py` tool descriptions

3. **Implement caching** in `tool_executor.py` for repeated queries

4. **Add feedback logging** to track 👍/👎 reactions

---

## Success Metrics

Track these metrics to measure AI improvements:

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Response accuracy | Unknown | 90% | User feedback (👍/👎) |
| Avg response time | ~8s | <5s | Metrics logging |
| Tool call efficiency | ~3 calls/query | ~2 calls | Metrics logging |
| User follow-up rate | Unknown | <20% | Thread analysis |
| Error rate | ~5% | <2% | Error logging |
