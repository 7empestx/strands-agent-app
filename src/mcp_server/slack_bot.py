"""Slack Bot integration for DevOps MCP Server.

Runs alongside the MCP server to handle Slack messages and route them
to the appropriate MCP tools.

Architecture: Claude Tool Use
- User message → Claude with tool definitions
- Claude decides which tool(s) to call
- Tool executes → Claude summarizes results
- No hardcoded intent classification or regex patterns

Uses Socket Mode for connection (no public endpoint needed).
"""

import json
import os
import re
import sys
import threading
import time
from datetime import datetime  # noqa: F401 - used in format_response

import boto3

# Add project root to path (go up from src/mcp_server to project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.lib.config_loader import get_env_mappings, get_service_registry, get_system_prompt
from src.lib.utils.secrets import get_secret
from src.mcp_server.clippy_tools import CLIPPY_TOOLS

# ============================================================================
# ERROR ALERTING
# ============================================================================

# Channel for Clippy error alerts
CLIPPY_DEV_CHANNEL = "C0A3RJA9LSJ"  # #clippy-ai-dev

_slack_client = None  # Will be set when SlackBot initializes


def alert_error(error_type: str, message: str, details: dict = None):
    """Post an error alert to #clippy-ai-dev channel.

    Args:
        error_type: Short error type (e.g., "Tool Failure", "API Error")
        message: Human-readable error message
        details: Optional dict with additional context
    """
    global _slack_client
    if not _slack_client:
        print(f"[Clippy Alert] {error_type}: {message} (no Slack client)")
        return

    try:
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"⚠️ *Clippy Error: {error_type}*\n{message}"}}]

        if details:
            detail_text = "\n".join([f"• *{k}*: `{v}`" for k, v in details.items()])
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": detail_text}})

        _slack_client.chat_postMessage(
            channel=CLIPPY_DEV_CHANNEL,
            text=f"⚠️ Clippy Error: {error_type} - {message}",
            blocks=blocks,
        )
    except Exception as e:
        print(f"[Clippy Alert] Failed to send alert: {e}")


# ============================================================================
# METRICS & LOGGING
# ============================================================================


class ClippyMetrics:
    """Track metrics for monitoring and debugging."""

    def __init__(self):
        self.total_requests = 0
        self.truncations = 0
        self.tool_limit_hits = 0
        self.tool_usage = {}
        self.errors = 0
        self.response_times = []
        self._lock = threading.Lock()

    def record_request(
        self, duration_ms: float, tools_used: list, was_truncated: bool, hit_limit: bool, error: bool = False
    ):
        with self._lock:
            self.total_requests += 1
            self.response_times.append(duration_ms)
            if was_truncated:
                self.truncations += 1
            if hit_limit:
                self.tool_limit_hits += 1
            if error:
                self.errors += 1
            for tool in tools_used:
                self.tool_usage[tool] = self.tool_usage.get(tool, 0) + 1

    def get_stats(self) -> dict:
        with self._lock:
            avg_response = (
                sum(self.response_times[-100:]) / len(self.response_times[-100:]) if self.response_times else 0
            )
            return {
                "total_requests": self.total_requests,
                "truncations": self.truncations,
                "truncation_rate": f"{100 * self.truncations / max(1, self.total_requests):.1f}%",
                "tool_limit_hits": self.tool_limit_hits,
                "tool_limit_rate": f"{100 * self.tool_limit_hits / max(1, self.total_requests):.1f}%",
                "errors": self.errors,
                "avg_response_ms": f"{avg_response:.0f}",
                "tool_usage": dict(sorted(self.tool_usage.items(), key=lambda x: -x[1])),
            }

    def log_summary(self):
        stats = self.get_stats()
        print(
            f"[Clippy Metrics] Requests: {stats['total_requests']} | "
            f"Truncations: {stats['truncations']} ({stats['truncation_rate']}) | "
            f"Tool limits: {stats['tool_limit_hits']} ({stats['tool_limit_rate']}) | "
            f"Errors: {stats['errors']} | "
            f"Avg response: {stats['avg_response_ms']}ms"
        )


# Global metrics instance
_metrics = ClippyMetrics()


def get_metrics() -> ClippyMetrics:
    return _metrics


# ============================================================================
# CLAUDE TOOL USE - Core Architecture
# ============================================================================

# Bedrock client (reused across calls)
_bedrock_client = None


def get_bedrock_client():
    """Get or create Bedrock runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")
    return _bedrock_client


# CLIPPY_TOOLS is now imported from clippy_tools.py
# System prompt, service registry, and env mappings are loaded from S3 via config_loader

# ============================================================================
# PROMPT ENHANCEMENT
# ============================================================================


def _detect_suspicious_request(message: str) -> dict | None:
    """Detect potentially suspicious requests that need security escalation.

    Returns dict with warning info if suspicious, None otherwise.
    """
    import re

    message_lower = message.lower()

    # Suspicious keywords and patterns
    suspicious_patterns = [
        # Legal/subpoena related
        (r"\b(subpoena|court\s*order|legal\s*request|warrant|discovery)\b", "legal_request"),
        # Data export/extraction
        (r"\b(export|dump|extract|download)\b.*(customer|user|merchant|pii|data|records)", "data_export"),
        (r"\b(customer|user|merchant)\b.*(export|dump|extract|download|list|all)", "data_export"),
        # Bulk access
        (r"\b(all|bulk|mass|every)\b.*(customer|user|merchant|transaction|payment)", "bulk_access"),
        # Credentials/access bypass
        (r"\b(bypass|circumvent|override|skip)\b.*(auth|security|access|permission)", "security_bypass"),
        # Social engineering red flags
        (r"(urgent|immediately|right\s*now|asap).*(access|data|export|credentials)", "urgency_pressure"),
        (r"(ceo|cfo|executive|boss)\s*(asked|wants|needs|said)", "authority_pressure"),
        # Database access
        (r"\b(database|db)\b.*(dump|export|backup|access|query)", "database_access"),
        # PII/sensitive data
        (r"\b(ssn|social\s*security|credit\s*card|bank\s*account|password)", "pii_access"),
    ]

    for pattern, category in suspicious_patterns:
        if re.search(pattern, message_lower):
            return {
                "category": category,
                "warning": f"⚠️ SECURITY: This request appears to involve {category.replace('_', ' ')}. "
                "Clippy should escalate to proper channels rather than assist directly.",
            }

    return None


def enhance_prompt_with_ai(message: str) -> str:
    """Use Claude Haiku to extract structured context from user message.

    Extracts:
    - Intent (what the user wants to do)
    - Services mentioned (with full names)
    - Environment (prod/staging/dev)
    - Time range (if any)
    - Urgency level
    - Key entities (ticket IDs, PR numbers, incident IDs, etc.)
    - Security concerns (suspicious requests)

    Returns the original message with AI-extracted context appended.
    """
    from datetime import datetime

    # Check for suspicious requests first
    suspicious = _detect_suspicious_request(message)
    if suspicious:
        print(f"[Clippy] SECURITY: Suspicious request detected - {suspicious['category']}")
        return f"{message}\n\n---\n{suspicious['warning']}"

    # Get current date context for the AI
    now = datetime.now()
    date_context = f"Today is {now.strftime('%A, %B %d, %Y')}. Current time: {now.strftime('%H:%M')}."

    # Build the extraction prompt
    extraction_prompt = f"""Extract structured information from this DevOps Slack message.

{date_context}

Known services and their aliases:
- cast-core-service (aliases: cast, cast-core, castcore) - Lambda: mrrobot-cast-core-[env]
- cast-app (aliases: cast-app, castapp)
- emvio-dashboard-app (aliases: dashboard, emvio-dashboard)
- emvio-gateway (aliases: gateway, emvio-gateway)
- cforce-service (aliases: cforce, c-force)
- mrrobot-auth-rest (aliases: auth, mrrobot-auth, auth-rest) - Lambda: mrrobot-auth-[env]
- emvio-underwriting-service (aliases: underwriting)
- emvio-retail-iframe-app (aliases: retail-iframe, retail iframe)

Environments: prod/production, staging/stage, dev/development, sandbox, devopslocal

USER MESSAGE:
{message}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "intent": "brief description of what user wants",
  "services": ["full-service-name-1"],
  "environment": "production|staging|development|sandbox|null",
  "time_range": {{
    "description": "human readable (e.g., 'past 4 hours', 'this week')",
    "hours_back": number or null
  }},
  "urgency": "high|medium|low",
  "entities": {{
    "ticket_ids": ["DEVOPS-123"],
    "pr_ids": [123],
    "incident_ids": ["P123ABC"],
    "urls": ["any relevant URLs"]
  }},
  "clarifications_needed": ["any ambiguities that might need clarifying"]
}}"""

    try:
        client = get_bedrock_client()

        response = client.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": extraction_prompt}],
                }
            ),
        )

        result = json.loads(response["body"].read())
        ai_response = result.get("content", [{}])[0].get("text", "{}")

        # Parse the JSON response
        try:
            extracted = json.loads(ai_response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response if it has extra text
            import re

            json_match = re.search(r"\{.*\}", ai_response, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group())
            else:
                print(f"[Clippy] AI enhancement failed to parse: {ai_response[:200]}")
                return message

        # Build context string from extracted info
        context_parts = []

        if extracted.get("intent"):
            context_parts.append(f"Intent: {extracted['intent']}")

        if extracted.get("services"):
            context_parts.append(f"Services: {', '.join(extracted['services'])}")

        if extracted.get("environment"):
            context_parts.append(f"Environment: {extracted['environment']}")

        if extracted.get("time_range", {}).get("description"):
            tr = extracted["time_range"]
            time_str = tr["description"]
            if tr.get("hours_back"):
                time_str += f" (~{tr['hours_back']} hours)"
            context_parts.append(f"Time range: {time_str}")

        if extracted.get("urgency") == "high":
            context_parts.append("Urgency: HIGH - prioritize speed")

        entities = extracted.get("entities", {})
        if entities.get("ticket_ids"):
            context_parts.append(f"Jira tickets: {', '.join(entities['ticket_ids'])}")
        if entities.get("pr_ids"):
            context_parts.append(f"PR IDs: {', '.join(map(str, entities['pr_ids']))}")
        if entities.get("incident_ids"):
            context_parts.append(f"PagerDuty incidents: {', '.join(entities['incident_ids'])}")

        if extracted.get("clarifications_needed"):
            context_parts.append(f"May need clarification: {'; '.join(extracted['clarifications_needed'])}")

        if context_parts:
            context = "\n".join(f"  - {p}" for p in context_parts)
            enhanced = f"{message}\n\n---\nAI-extracted context:\n{context}"
            print(f"[Clippy] AI enhancement added {len(context_parts)} context items")
            return enhanced

        return message

    except Exception as e:
        print(f"[Clippy] AI enhancement error: {e}")
        # Fall back to original message on any error
        return message


def enhance_prompt(message: str) -> str:
    """Enhance user message with additional context for better tool usage.

    Uses AI (Claude Haiku) to extract structured information from the message.
    Falls back to rule-based extraction if AI fails.
    """
    # Try AI-powered enhancement first
    enhanced = enhance_prompt_with_ai(message)
    if enhanced != message:
        return enhanced

    # Fallback: Simple rule-based enhancement
    from datetime import datetime, timedelta

    enhancements = []
    message_lower = message.lower()

    # Time parsing
    now = datetime.now()
    time_context = None

    if "this week" in message_lower:
        monday = now - timedelta(days=now.weekday())
        time_context = f"Time: 'this week' = since {monday.strftime('%Y-%m-%d')}"
    elif "today" in message_lower:
        time_context = f"Time: 'today' = {now.strftime('%Y-%m-%d')}"
    elif "yesterday" in message_lower:
        yesterday = now - timedelta(days=1)
        time_context = f"Time: 'yesterday' = {yesterday.strftime('%Y-%m-%d')}"

    if time_context:
        enhancements.append(time_context)

    # Service mapping (loaded from S3)
    service_registry = get_service_registry()
    for service_key, info in service_registry.items():
        for alias in info.get("aliases", []):
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, message_lower):
                enhancements.append(f"Service: {alias} = {info['full_name']}")
                break

    # Environment (loaded from S3)
    env_mappings = get_env_mappings()
    for env_short, env_full in env_mappings.items():
        pattern = r"\b" + re.escape(env_short) + r"\b"
        if re.search(pattern, message_lower):
            enhancements.append(f"Environment: {env_full}")
            break

    if enhancements:
        context = "\n".join(f"  - {e}" for e in enhancements)
        return f"{message}\n\n---\nContext:\n{context}"

    return message


def invoke_claude_with_tools(
    message: str, thread_context: list = None, max_tokens: int = 600, max_tool_calls: int = 10
) -> dict:
    """Invoke Claude with tool definitions and handle tool calls.

    This is the core of the new architecture:
    1. Enhance the message with context (time, service info, env)
    2. Send message to Claude with tool definitions
    3. If Claude wants to use a tool, execute it
    4. Send tool result back to Claude
    5. Repeat until Claude gives final response (up to max_tool_calls)

    Returns:
        dict with 'response' (text) and optionally 'tool_used', 'tool_result'
    """
    start_time = time.time()
    client = get_bedrock_client()
    any_truncated = False

    # Enhance the message with additional context
    enhanced_message = enhance_prompt(message)
    if enhanced_message != message:
        print(f"[Clippy] Prompt enhanced with context")

    # Build messages with optional thread context
    messages = []
    if thread_context:
        # Add thread context as assistant/user turns (last 10 messages for good context)
        for ctx in thread_context[-10:]:
            if ctx.startswith("Clippy:"):
                role = "assistant"
                content = ctx[8:]  # Remove "Clippy: " prefix
            else:
                role = "user"
                content = ctx[6:] if ctx.startswith("User: ") else ctx  # Remove "User: " prefix if present

            # Skip empty messages
            if content.strip():
                messages.append({"role": role, "content": content})

    # Add current message (with enhancements)
    messages.append({"role": "user", "content": enhanced_message})

    tools_used = []
    tool_results = []

    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": get_system_prompt(),  # Loaded from S3
            "messages": messages,
            "tools": CLIPPY_TOOLS,
        }

        # Loop for multi-turn tool calling
        for turn in range(max_tool_calls + 1):
            response = client.invoke_model(
                modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
                body=json.dumps(body),
            )

            result = json.loads(response["body"].read())
            stop_reason = result.get("stop_reason", "")
            content = result.get("content", [])

            print(f"[Clippy] Turn {turn + 1} - stop_reason: {stop_reason}, content blocks: {len(content)}")

            # If Claude is done (end_turn or max_tokens), extract final response
            if stop_reason != "tool_use":
                final_text = ""
                for block in content:
                    if block.get("type") == "text":
                        final_text += block.get("text", "")

                # Record metrics
                duration_ms = (time.time() - start_time) * 1000
                _metrics.record_request(duration_ms, tools_used, any_truncated, hit_limit=False)
                if _metrics.total_requests % 10 == 0:
                    _metrics.log_summary()

                return {
                    "response": final_text or "I found some results but had trouble summarizing them.",
                    "tool_used": tools_used[-1] if tools_used else None,
                    "tool_result": tool_results[-1] if tool_results else None,
                    "all_tools_used": tools_used,
                    "was_truncated": any_truncated,
                }

            # Claude wants to use tool(s) - may be multiple in parallel
            tool_use_blocks = [block for block in content if block.get("type") == "tool_use"]

            if not tool_use_blocks:
                break

            # Check for respond_directly first
            for tool_use in tool_use_blocks:
                if tool_use.get("name") == "respond_directly":
                    return {
                        "response": tool_use.get("input", {}).get("message", "How can I help?"),
                        "tool_used": None,
                        "tool_result": None,
                    }

            # Execute all tools and collect results
            tool_result_contents = []
            for tool_use in tool_use_blocks:
                tool_name = tool_use.get("name")
                tool_input = tool_use.get("input", {})
                tool_id = tool_use.get("id")

                print(f"[Clippy] Tool call {turn + 1}: {tool_name}({tool_input})")

                # Execute the tool
                tool_result = execute_tool(tool_name, tool_input)
                tools_used.append(tool_name)
                tool_results.append(tool_result)

                # Serialize tool result and check if truncation needed
                tool_result_str = json.dumps(tool_result, default=str)
                was_truncated = len(tool_result_str) > 8000
                if was_truncated:
                    any_truncated = True
                    print(f"[Clippy] WARNING: {tool_name} result truncated from {len(tool_result_str)} to 8000 chars")
                    tool_result_str = (
                        tool_result_str[:7800]
                        + "\n\n[WARNING: Results truncated. There may be additional data not shown. Ask user to narrow their query if needed.]"
                    )

                tool_result_contents.append({"type": "tool_result", "tool_use_id": tool_id, "content": tool_result_str})

            # Add assistant's response and all tool results to messages
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": tool_result_contents})

            # Update body for next turn
            body["messages"] = messages
            body["max_tokens"] = 1200  # More tokens for summaries

        # If we hit max turns, return what we have
        print(f"[Clippy] WARNING: Hit max tool calls limit ({max_tool_calls}). Tools used: {tools_used}")
        duration_ms = (time.time() - start_time) * 1000
        _metrics.record_request(duration_ms, tools_used, any_truncated, hit_limit=True)
        _metrics.log_summary()

        return {
            "response": "I ran multiple searches but need more information to help fully. Here's what I found so far - could you provide more specific details about the issue?",
            "tool_used": tools_used[-1] if tools_used else None,
            "tool_result": tool_results[-1] if tool_results else None,
            "all_tools_used": tools_used,
            "was_truncated": any_truncated,
            "hit_tool_limit": True,
        }

        # No tool use - just return Claude's direct response
        text_response = ""
        for block in content:
            if block.get("type") == "text":
                text_response += block.get("text", "")

        return {
            "response": text_response or "I'm not sure how to help with that. Could you rephrase?",
            "tool_used": None,
            "tool_result": None,
        }

    except Exception as e:
        print(f"[Clippy] Error in invoke_claude_with_tools: {e}")
        import traceback

        traceback.print_exc()

        # Record error metrics
        duration_ms = (time.time() - start_time) * 1000
        _metrics.record_request(duration_ms, [], was_truncated=False, hit_limit=False, error=True)

        # Alert to dev channel
        alert_error(
            "Claude API Error",
            f"Error processing request: {str(e)[:200]}",
            {"message_preview": message[:100], "duration_ms": f"{duration_ms:.0f}"},
        )

        return {
            "response": f"I encountered an error: {str(e)[:100]}. Please try again.",
            "tool_used": None,
            "tool_result": None,
            "error": True,
        }


def _summarize_logs(logs: list, max_logs: int = 20) -> list:
    """Summarize log entries to reduce token usage.

    Extracts key fields and truncates long messages.
    """
    summarized = []
    for log in logs[:max_logs]:
        entry = {
            "timestamp": log.get("timestamp", log.get("@timestamp", "")),
            "level": log.get("level", log.get("severity", "")),
            "service": log.get("logGroup", log.get("service", ""))[-50:],  # Last 50 chars
        }
        # Get message and truncate
        msg = log.get("message", log.get("msg", str(log)))
        if isinstance(msg, str):
            entry["message"] = msg[:500] + "..." if len(msg) > 500 else msg
        else:
            entry["message"] = str(msg)[:500]
        summarized.append(entry)
    return summarized


def _compact_tool_result(tool_name: str, result: dict) -> dict:
    """Compact tool results to reduce size while preserving key information.

    This is critical for preventing truncation when sending results to Claude.
    Each tool type gets specific compaction logic to preserve the most useful info.
    """
    if tool_name in ["search_logs", "get_recent_errors"]:
        # Summarize log results
        if "logs" in result:
            result["logs"] = _summarize_logs(result["logs"], max_logs=15)
            result["_compacted"] = True
        if "errors_by_service" in result:
            # Keep only top 5 services, 5 errors each
            errors_by_service = result["errors_by_service"]
            compacted = {}
            for svc, data in list(errors_by_service.items())[:5]:
                if isinstance(data, dict) and "recent_errors" in data:
                    data["recent_errors"] = _summarize_logs(data["recent_errors"], max_logs=5)
                compacted[svc] = data
            result["errors_by_service"] = compacted
            result["_compacted"] = True

    elif tool_name == "search_cloudwatch_logs":
        # Summarize CloudWatch results
        if "results" in result:
            result["results"] = _summarize_logs(result["results"], max_logs=15)
            result["_compacted"] = True

    elif tool_name == "search_code":
        # Truncate code snippets
        if "results" in result:
            for r in result["results"]:
                if "content" in r and len(r["content"]) > 800:
                    r["content"] = r["content"][:800] + "\n... [truncated]"
            result["_compacted"] = True

    elif tool_name == "search_devops_history":
        # Summarize Slack history results
        if "results" in result:
            for r in result["results"]:
                if "content" in r and len(r["content"]) > 600:
                    r["content"] = r["content"][:600] + "... [more context available]"
            result["_compacted"] = True

    elif tool_name == "get_pr_details":
        # Limit files shown and truncate descriptions
        if "files_changed" in result and len(result["files_changed"]) > 10:
            result["files_changed"] = result["files_changed"][:10]
            result["more_files"] = True
        if "description" in result and len(result["description"]) > 500:
            result["description"] = result["description"][:500] + "..."
        # Keep comments summary but truncate individual comments
        if "comments" in result:
            for c in result.get("comments", [])[:5]:
                if "content" in c and len(c["content"]) > 200:
                    c["content"] = c["content"][:200] + "..."
            if len(result["comments"]) > 5:
                result["comments"] = result["comments"][:5]
                result["more_comments"] = True

    elif tool_name == "investigate_issue":
        # This returns a full report - keep key sections, summarize details
        if "logs" in result:
            result["logs"] = _summarize_logs(result["logs"], max_logs=10)
        if "recent_deploys" in result and len(result["recent_deploys"]) > 3:
            result["recent_deploys"] = result["recent_deploys"][:3]

    return result


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Execute an MCP tool and return the result.

    This maps Claude's tool calls to our actual MCP tool implementations.
    Results are compacted to reduce token usage.
    """
    result = _execute_tool_internal(tool_name, tool_input)

    # Compact results to reduce size (prevents truncation)
    if isinstance(result, dict) and "error" not in result:
        result = _compact_tool_result(tool_name, result)

    return result


def _execute_tool_internal(tool_name: str, tool_input: dict) -> dict:
    """Internal tool execution - returns raw results."""
    try:
        if tool_name == "search_logs":
            from src.lib.coralogix import handle_search_logs

            return handle_search_logs(
                query=tool_input.get("query", ""),
                hours_back=tool_input.get("hours_back", 4),
                limit=tool_input.get("limit", 50),
            )

        elif tool_name == "get_recent_errors":
            from src.lib.coralogix import handle_get_recent_errors

            return handle_get_recent_errors(
                service_name=tool_input.get("service", "all"), hours_back=tool_input.get("hours_back", 4), limit=50
            )

        elif tool_name == "search_code":
            from src.lib.code_search import search_knowledge_base

            return search_knowledge_base(
                query=tool_input.get("query", ""), num_results=tool_input.get("num_results", 5)
            )

        elif tool_name == "get_pipeline_status":
            from src.lib.bitbucket import get_pipeline_status

            return get_pipeline_status(repo_slug=tool_input.get("repo", ""), limit=tool_input.get("limit", 5))

        elif tool_name == "get_pipeline_details":
            from src.lib.bitbucket import get_pipeline_details

            repo = tool_input.get("repo", "")
            if "/" in repo:
                repo = repo.split("/")[-1]
            return get_pipeline_details(repo_slug=repo, pipeline_id=tool_input.get("pipeline_id", 0))

        elif tool_name == "aws_cli":
            from src.lib.aws_cli import run_aws_command

            return run_aws_command(command=tool_input.get("command", ""), region=tool_input.get("region", "us-east-1"))

        elif tool_name == "list_open_prs":
            from src.lib.bitbucket import get_open_prs

            return get_open_prs(repo_slug=tool_input.get("repo", ""), limit=tool_input.get("limit", 5))

        elif tool_name == "get_pr_details":
            from src.lib.bitbucket import get_pr_details

            # Strip workspace prefix if Claude included it (e.g., "mrrobot-labs/repo" -> "repo")
            repo = tool_input.get("repo", "")
            if "/" in repo:
                repo = repo.split("/")[-1]
            return get_pr_details(repo_slug=repo, pr_id=tool_input.get("pr_id", 0))

        elif tool_name == "list_alarms":
            from src.lib.cloudwatch import list_alarms

            return list_alarms(state_value=tool_input.get("state"))

        elif tool_name == "search_cloudwatch_logs":
            from src.lib.cloudwatch import list_log_groups, query_logs

            service = tool_input.get("service", "")
            search_term = tool_input.get("query", "error")
            hours = tool_input.get("hours_back", 4)

            # Try to find matching log group
            base_name = service.replace("-staging", "-dev").replace("-prod", "-dev")
            search_prefix = f"/aws/lambda/{base_name.split('-')[0]}" if not service.startswith("/") else service

            # List available log groups matching the pattern
            available = list_log_groups(prefix=search_prefix)
            matching_groups = [g["name"] for g in available.get("log_groups", [])]

            # Try exact match first, then partial
            log_group = f"/aws/lambda/{service}" if not service.startswith("/") else service

            if log_group not in matching_groups:
                # Try to find a close match
                for g in matching_groups:
                    if base_name in g or service.split("-")[0] in g:
                        log_group = g
                        break
                else:
                    # No match found
                    return {
                        "error": f"Log group not found: {log_group}",
                        "note": "This service may be in a different AWS account (staging/prod vs dev)",
                        "available_groups": matching_groups[:10],
                        "suggestion": "Try checking Coralogix logs instead with search_logs",
                    }

            # Build query
            query = (
                f"fields @timestamp, @message | filter @message like /{search_term}/ | sort @timestamp desc | limit 50"
            )

            return query_logs(log_group=log_group, query=query, hours_back=hours)

        elif tool_name == "get_ecs_metrics":
            from src.lib.cloudwatch import get_ecs_service_metrics

            return get_ecs_service_metrics(
                cluster_name=tool_input.get("cluster", "mrrobot-ai-core"),
                service_name=tool_input.get("service", "mrrobot-mcp-server"),
            )

        elif tool_name == "get_service_info":
            # Use service registry (fast lookup from S3-cached data)
            from src.lib.config_loader import lookup_service

            service_name = tool_input.get("service_name", "")
            service_info = lookup_service(service_name)

            if service_info:
                # Found in registry - return rich info
                service_type = service_info.get("type", "unknown")
                return {
                    "service_name": service_name,
                    "found": True,
                    "key": service_info.get("key"),
                    "full_name": service_info.get("full_name"),
                    "type": service_type,
                    "tech_stack": service_info.get("tech_stack", []),
                    "description": service_info.get("description", ""),
                    "aliases": service_info.get("aliases", []),
                    "repo": service_info.get("repo", service_info.get("full_name")),
                    "suggestion": (
                        "Frontend app - check deploys and browser console for API errors."
                        if service_type == "frontend"
                        else (
                            "Backend service - check logs first, then recent deploys."
                            if service_type == "backend"
                            else (
                                "Library/tool - check if dependent services are affected."
                                if service_type in ("library", "tool")
                                else "Check both logs and deploys."
                            )
                        )
                    ),
                }
            else:
                # Not in registry - fall back to KB search
                from src.lib.code_search import search_knowledge_base

                results = search_knowledge_base(query=f"{service_name} package.json README", num_results=3)
                files_found = [r.get("file", "") for r in results.get("results", [])]

                return {
                    "service_name": service_name,
                    "found": False,
                    "message": f"Service '{service_name}' not found in registry (129 known services).",
                    "files_found": files_found[:3],
                    "suggestion": "This may be a new service or misspelled. Check the files found or try a different name.",
                }

        elif tool_name == "search_devops_history":
            # Search Slack history in the Knowledge Base
            from src.lib.code_search import search_knowledge_base

            query = tool_input.get("query", "")

            # Search with context that this is for past conversations
            results = search_knowledge_base(query=f"Slack conversation: {query}", num_results=5)

            # Filter to only slack-history results if possible
            slack_results = []
            for r in results.get("results", []):
                # Include all results but flag which are from slack
                is_slack = "slack-history" in r.get("full_path", "") or r.get("file", "").endswith(".txt")
                slack_results.append(
                    {
                        "source": "slack" if is_slack else "code",
                        "content": r.get("content", "")[:500],
                        "file": r.get("file", ""),
                        "score": r.get("score", 0),
                    }
                )

            if not slack_results:
                return {
                    "found": False,
                    "message": "No past conversations found matching that query.",
                    "suggestion": "Try a different search term or check if Slack history has been synced.",
                }

            return {
                "found": True,
                "query": query,
                "results": slack_results,
                "message": f"Found {len(slack_results)} past conversation(s) that might be relevant.",
            }

        elif tool_name == "investigate_issue":
            from src.lib.investigation_agent import investigate_issue

            return investigate_issue(
                service=tool_input.get("service", ""),
                environment=tool_input.get("environment"),
                description=tool_input.get("description"),
            )

        elif tool_name == "jira_search":
            from src.lib.jira import handle_search_jira

            return handle_search_jira(
                query=tool_input.get("query", ""),
                max_results=tool_input.get("max_results", 20),
            )

        elif tool_name == "jira_cve_tickets":
            from src.lib.jira import get_open_cve_issues

            return get_open_cve_issues(max_results=tool_input.get("max_results", 50))

        elif tool_name == "jira_get_ticket":
            from src.lib.jira import get_issue

            return get_issue(issue_key=tool_input.get("issue_key", ""))

        elif tool_name == "pagerduty_active_incidents":
            from src.lib.pagerduty import handle_active_incidents

            return handle_active_incidents()

        elif tool_name == "pagerduty_recent_incidents":
            from src.lib.pagerduty import handle_recent_incidents

            days = tool_input.get("days", 7)
            return handle_recent_incidents(days=days)

        elif tool_name == "pagerduty_incident_details":
            from src.lib.pagerduty import handle_incident_details

            return handle_incident_details(incident_id=tool_input.get("incident_id", ""))

        elif tool_name == "pagerduty_investigate":
            from src.lib.coralogix import handle_get_recent_errors
            from src.lib.pagerduty import extract_service_name_from_incident, handle_incident_details

            # Get incident details first
            incident = handle_incident_details(incident_id=tool_input.get("incident_id", ""))
            if "error" in incident:
                return incident

            # Try to extract service name and check logs
            service_name = extract_service_name_from_incident(incident)
            logs_result = None
            if service_name:
                try:
                    logs_result = handle_get_recent_errors(service=service_name, hours_back=4)
                except Exception as e:
                    logs_result = {"error": str(e)}

            return {
                "incident": incident,
                "service_detected": service_name,
                "related_logs": logs_result,
            }

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        print(f"[Clippy] Tool execution error: {e}")
        # Alert to dev channel for tool failures
        alert_error(
            "Tool Execution Error",
            f"Tool '{tool_name}' failed: {str(e)[:200]}",
            {"tool": tool_name, "input": str(tool_input)[:200]},
        )
        return {"error": str(e)}


# ============================================================================
# LEGACY HELPERS (kept for compatibility, will be removed)
# ============================================================================


def call_claude(prompt: str, max_tokens: int = 500) -> str:
    """Call Claude via Bedrock for simple prompts (legacy).

    For new code, use invoke_claude_with_tools() instead.
    """
    try:
        client = get_bedrock_client()

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = client.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps(body),
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    except Exception as e:
        print(f"[AI] Claude call failed: {e}")
        return None


def ai_classify_intent(message: str) -> dict:
    """Use AI to classify intent and extract entities from a message."""
    prompt = f"""Classify this DevOps request and extract key information.

MESSAGE: "{message}"

Respond in JSON only:
{{
  "intent": "log_search|alert_triage|code_search|pr_review|deploy_check|cloudwatch|access_request|greeting|general",
  "service": "service-name or null",
  "environment": "prod|staging|dev or null",
  "is_urgent": true/false,
  "is_vague": true/false,
  "summary": "one-line summary of what they want"
}}

Intent definitions:
- log_search: searching logs, troubleshooting issues, checking errors
- alert_triage: checking system status, recent errors across services
- code_search: finding code, configs, implementations
- pr_review: PR approval, code review requests
- deploy_check: recent deployments, pipeline status
- cloudwatch: metrics, alarms, AWS monitoring
- access_request: permissions, onboarding, SFTP access
- greeting: hi, hello, help
- general: unclear or other

JSON only, no explanation:"""

    result = call_claude(prompt, max_tokens=200)
    if result:
        try:
            # Extract JSON from response
            json_match = re.search(r"\{[^{}]+\}", result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError):
            pass
    return None


def get_thread_context(client, channel: str, thread_ts: str, limit: int = 15) -> list:
    """Fetch previous messages from a Slack thread for context.

    Returns structured context that preserves:
    - Who said what (user vs bot)
    - Tool findings from bot responses
    - Enough history for follow-up questions
    """
    try:
        result = client.conversations_replies(
            channel=channel,
            ts=thread_ts,
            limit=limit,
        )
        messages = result.get("messages", [])

        # Get bot user ID to identify bot messages
        try:
            auth_response = client.auth_test()
            bot_user_id = auth_response.get("user_id")
        except Exception:
            bot_user_id = None

        # Format for context (skip the current message which is last)
        context = []
        for msg in messages[:-1]:  # Exclude current message
            user_id = msg.get("user", "")
            bot_id = msg.get("bot_id", "")
            text = msg.get("text", "")[:500]  # More context per message

            # Determine if this is from the bot
            is_bot = bool(bot_id) or (bot_user_id and user_id == bot_user_id)
            role = "Clippy" if is_bot else "User"

            context.append(f"{role}: {text}")

        return context
    except Exception as e:
        print(f"[SlackBot] Error fetching thread context: {e}")
        return []


def ai_generate_response(
    message: str,
    service: str = None,
    env: str = None,
    thread_context: list = None,
    intent: str = None,
) -> str:
    """Use AI to generate a contextual response with thread history."""

    # Build context from thread
    context_text = ""
    if thread_context:
        context_text = "\n".join(thread_context[-5:])  # Last 5 messages
        context_text = f"\nPREVIOUS CONVERSATION:\n{context_text}\n"

    prompt = f"""You are Clippy, a friendly DevOps AI assistant in Slack.
{context_text}
CURRENT MESSAGE: "{message}"
Service detected: {service or 'not specified'}
Environment: {env or 'not specified'}
Detected intent: {intent or 'unknown'}

Generate a helpful response that:
1. If this is a follow-up, acknowledge the context and continue the conversation
2. If they're asking for clarification, provide specific guidance
3. If they want action, confirm what you're doing

Keep it under 150 words. Use Slack formatting (*bold*, `code`).
Be conversational but professional. Reference previous context when relevant.

Response:"""

    result = call_claude(prompt, max_tokens=300)
    return result if result else None


def ai_generate_clarification(message: str, service: str = None, env: str = None) -> str:
    """Use AI to generate a contextual clarifying response."""
    prompt = f"""You are Clippy, a friendly DevOps AI assistant in Slack.

A user said: "{message}"
Service detected: {service or 'unknown'}
Environment: {env or 'unknown'}

Generate a brief, helpful response that:
1. Acknowledges their issue warmly
2. Asks 1-2 clarifying questions to help faster
3. Offers 2-3 specific commands they can try

Keep it under 150 words. Use Slack formatting (*bold*, `code`).
Be conversational but professional. Show you understand DevOps.

Response:"""

    result = call_claude(prompt, max_tokens=300)
    return result if result else None


def ai_summarize_logs(logs: list, query: str) -> str:
    """Use AI to summarize log results and provide insights."""
    if not logs:
        return None

    # Take first 10 logs for context
    log_sample = logs[:10]
    log_text = "\n".join([f"- {log.get('message', str(log))[:200]}" for log in log_sample])

    prompt = f"""Analyze these log entries and provide a brief summary.

QUERY: "{query}"
TOTAL RESULTS: {len(logs)}

LOG SAMPLES:
{log_text}

Provide:
1. One-line summary of what's happening
2. Key patterns or issues detected
3. Suggested next steps

Keep it under 100 words. Use Slack formatting.

Analysis:"""

    result = call_claude(prompt, max_tokens=250)
    return result if result else None


def ai_review_pr(pr_details: dict) -> str:
    """Use AI to provide a brief PR review summary."""
    files = pr_details.get("files_changed", [])
    files_text = "\n".join([f"- {f['path']} (+{f['lines_added']}/-{f['lines_removed']})" for f in files[:15]])

    prompt = f"""Review this Pull Request and provide a brief assessment.

PR: {pr_details.get('title', '')}
Author: {pr_details.get('author', '')}
Branch: {pr_details.get('source_branch', '')} → {pr_details.get('dest_branch', '')}
Description: {pr_details.get('description', 'No description')[:300]}

FILES CHANGED ({pr_details.get('total_files', 0)} total):
{files_text}

Provide a 2-3 sentence assessment:
1. What does this PR do?
2. Any concerns based on file names/scope?
3. Recommendation (looks good to review / needs attention / large change)

Keep it brief. Use Slack formatting.

Assessment:"""

    result = call_claude(prompt, max_tokens=200)
    return result if result else None


# ============================================================================
# CLIPPY PERSONALITY
# ============================================================================


def _convert_to_slack_markdown(text: str) -> str:
    """Convert standard markdown to Slack mrkdwn format.

    Slack uses different markdown:
    - *bold* instead of **bold**
    - _italic_ instead of *italic*
    - ~strikethrough~ (same)
    - `code` (same)
    - ```code block``` (same)
    """
    import re

    # Convert **bold** to *bold* (but not inside code blocks)
    # First, protect code blocks
    code_blocks = []

    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    # Save code blocks
    result = re.sub(r"```[\s\S]*?```", save_code_block, text)
    result = re.sub(r"`[^`]+`", save_code_block, result)

    # Convert **bold** to *bold*
    result = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", result)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        result = result.replace(f"__CODE_BLOCK_{i}__", block)

    return result


def _redact_secrets(text: str) -> str:
    """Redact potential secrets from response text."""
    import re

    # Patterns that look like secrets
    patterns = [
        # PASSWORD='value' or PASSWORD="value" or PASSWORD=value
        (
            r"(PASSWORD|PASS|PWD|SECRET|TOKEN|KEY|CREDENTIAL|API_KEY|APIKEY|AUTH)\s*[=:]\s*['\"]?([^'\"\s,\n]{6,})['\"]?",
            r"\1=***REDACTED***",
        ),
        # Bearer tokens
        (r"(Bearer\s+)([A-Za-z0-9_\-\.]{20,})", r"\1***REDACTED***"),
        # AWS keys
        (r"(AKIA[A-Z0-9]{16})", r"***AWS_KEY_REDACTED***"),
        # Generic long alphanumeric strings that look like secrets (after = or :)
        (
            r"(['\"]?(?:password|secret|token|key|credential)['\"]?\s*[=:]\s*['\"]?)([A-Za-z0-9_\-\.]{12,})(['\"]?)",
            r"\1***REDACTED***\3",
        ),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def _get_acknowledgment(message: str) -> str:
    """Generate a context-aware acknowledgment using Claude."""
    try:
        client = get_bedrock_client()

        prompt = f"""Generate a brief 2-5 word acknowledgment for this DevOps Slack message. Be casual and specific to what they're asking about. No emoji. No punctuation except "..." at the end.

Examples:
- "check this PR" → "Checking that PR..."
- "seeing 504 errors" → "Investigating those 504s..."
- "recent deploys for auth service" → "Checking auth deploys..."
- "help with SFTP access" → "Looking into SFTP..."

Message: "{message[:200]}"

Acknowledgment:"""

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = client.invoke_model(
            modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(body),
        )

        result = json.loads(response["body"].read())
        ack = result["content"][0]["text"].strip().strip('"')

        # Ensure it ends with ...
        if not ack.endswith("..."):
            ack = ack.rstrip(".") + "..."

        return ack

    except Exception as e:
        print(f"[Clippy] Ack generation failed: {e}")
        return "On it..."


CLIPPY_INTRO = """👋 Hi! I'm Clippy, your DevOps assistant.

I can help you:
• 🔍 Search logs across all environments
• 🚨 Investigate production issues
• 💻 Find code and configurations
• 📊 Check CloudWatch metrics and alarms

Just tell me what's going on!"""

TROUBLESHOOTING_FOLLOWUP = """
💡 *Want me to dig deeper?* Try:
• "Show me more details on that error"
• "Compare staging vs dev logs"
• "What changed recently in this service?"
• "Check CloudWatch metrics for this service"
"""

# Footer for responses
CLIPPY_FOOTER = """
---
_🚧 Clippy is a work in progress! <https://ai-agent.mrrobot.dev/?page=feedback|Give feedback> to help improve._
_💬 I only respond once per thread. Use `@Clippy-ai` to continue the conversation._"""

# Keywords that indicate a CLEAR, actionable request (auto-execute)
CLEAR_ACTION_KEYWORDS = [
    "search logs",
    "find logs",
    "show logs",
    "check logs",
    "get logs",
    "search for",
    "show me the",
    "list",
    "list alarms",
    "check alarms",
    "show alarms",
    "what errors",
    "recent errors",
    "show errors",
]

# Keywords that indicate VAGUE/conversational request (ask first)
VAGUE_KEYWORDS = [
    "having an issue",
    "having a problem",
    "something's wrong",
    "not working",
    "broken",
    "help me",
    "can you help",
    "figure out",
    "investigate",
    "look into",
    "debug",
    "can i get someone",
    "need help",
    "we need",
]


def is_clear_request(message: str) -> bool:
    """Check if the request is clear and actionable (should auto-execute)."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in CLEAR_ACTION_KEYWORDS)


def is_vague_request(message: str) -> bool:
    """Check if the request is vague/conversational (should ask questions first)."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in VAGUE_KEYWORDS)


def ai_extract_entities(message: str) -> dict:
    """Use AI to extract service names, environments, and other entities from a message.

    No hardcoded patterns - Claude understands context and variations.
    """
    prompt = f"""Extract entities from this DevOps request. Be flexible with naming -
users might say "emvio dashboard" meaning "emvio-dashboard-app" or "cast core" meaning "cast-core".

MESSAGE: "{message}"

Return JSON only:
{{
  "service": "extracted-service-name or null (normalize to kebab-case like emvio-dashboard-app)",
  "environment": "prod|staging|dev|sandbox or null",
  "error_type": "description of error if mentioned, or null",
  "timeframe": "when it started if mentioned, or null",
  "action_requested": "what the user wants (troubleshoot, approve PR, check logs, etc.)"
}}

JSON only, no explanation:"""

    result = call_claude(prompt, max_tokens=200)
    if result:
        try:
            json_match = re.search(r"\{[^{}]+\}", result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"[AI] Entity extraction failed to parse: {e}")
    return {}


def build_clarifying_response(message: str, context: list = None) -> dict:
    """Use AI to generate a contextual, conversational clarifying response.

    No hardcoded templates - Claude generates natural responses.
    """
    # First extract what we know
    entities = ai_extract_entities(message)

    context_str = ""
    if context:
        context_str = f"\nPREVIOUS MESSAGES IN THREAD:\n" + "\n".join([f"- {m}" for m in context[-3:]])

    prompt = f"""You are Clippy, a helpful DevOps AI assistant. A user asked for help but their request
needs clarification before you can take action.

USER MESSAGE: "{message}"
{context_str}
EXTRACTED INFO: {json.dumps(entities)}

Generate a friendly, conversational response that:
1. Acknowledges what you understood from their request
2. Asks 1-2 specific clarifying questions based on what's missing
3. Offers 2-3 specific actions you could take immediately

Keep it concise (under 150 words). Use Slack formatting (*bold*, `code`).
Be warm and helpful, like a friendly colleague. Don't be robotic.

Response:"""

    result = call_claude(prompt, max_tokens=300)
    if result:
        return {"response": f"🤔 {result}"}

    # Fallback if AI fails
    service = entities.get("service", "your service")
    return {
        "response": f"🤔 I'd like to help with `{service}`! Can you tell me:\n• What error or behavior are you seeing?\n• When did this start?\n\nOr I can start checking logs right away!"
    }


# ============================================================================
# LEGACY CODE - Kept for reference, no longer used with Claude Tool Use
# ============================================================================
# The code below (INTENT_PATTERNS, classify_intent, route_to_tool, format_response)
# was replaced by invoke_claude_with_tools() which lets Claude decide what to do.
# This legacy code can be removed once Claude Tool Use is confirmed working.

INTENT_PATTERNS = {
    # Order matters - check admin commands first, then greeting, then specific intents
    "admin_toggle": [
        r"auto.?reply\s+(on|off|enable|disable)",
        r"(enable|disable)\s+auto.?reply",
    ],
    "greeting": [
        r"^(hi|hello|hey|howdy|sup|yo)$",
        r"^(hi|hello|hey)[\s!.,]*$",
        r"good (morning|afternoon|evening)",
    ],
    # Log/troubleshooting - expanded to catch more debug scenarios
    "log_search": [
        r"(search|query|find).*logs?",
        r"logs?.*(search|query|find)",
        r"(coralogix|dataprime)",
        r"(check|show).*logs?",
        # NEW: Troubleshooting patterns
        r"(issue|problem|bug|broken|not working|failing).*(on|in|with)",
        r"(staging|sandbox|dev|prod).*(issue|problem|error|bug)",
        r"(emvio|cast|mrrobot)-\w+.*(issue|problem|error|not)",
        r"(debug|troubleshoot|investigate|figure out)",
        r"what('s| is).*happening",
        r"(help|assist).*(issue|problem|error|debug)",
    ],
    "alert_triage": [
        r"(500|alert|pagerduty|incident|outage|down)",
        r"(check|what.*happening|status).*(service|error)",
        r"(prod|production).*(error|issue|problem)",
        r"(critical|urgent|emergency)",
        r"error.*(in|on|from)",
    ],
    "pr_review": [
        r"(approve|review|merge).*pr",
        r"pull.?request",
        r"bitbucket\.org.*/pull-requests/",
    ],
    "code_search": [
        r"(where|find|search|how).*(code|config|implementation)",
        r"(csp|cors|env|terraform|serverless)",
        r"search.*repo",
        r"(find|show|get).*file",
    ],
    "deploy_check": [
        r"(recent|last|latest).*(deploy|deploys|pipeline|build)",
        r"(deploy|deploys|pipeline|build).*(status|history|recent)",
        r"what.*deploy",
        r"what.*changed",
        r"(check|show).*pipeline",
        r"deploy.*for",
        r"pipeline.*for",
    ],
    "access_request": [
        r"(sftp|ssh|access|permission|onboard|offboard)",
        r"(add|remove|create).*user",
        r"(atlassian|jira|confluence).*access",
    ],
    "cloudwatch": [
        r"(cloudwatch|metrics|alarms?|cpu|memory)",
        r"(ecs|lambda).*(metrics|status|health)",
    ],
}


def classify_intent(message: str, use_ai: bool = True) -> tuple:
    """Classify the intent of a Slack message.

    Args:
        message: The user's message
        use_ai: Whether to use AI classification (slower but smarter)

    Returns:
        tuple of (intent, ai_context) where ai_context contains extracted entities
    """
    ai_context = None

    # Try AI classification first (for complex messages)
    if use_ai and len(message) > 20:
        ai_result = ai_classify_intent(message)
        if ai_result:
            print(f"[SlackBot] AI classification: {ai_result}")
            ai_context = ai_result
            intent = ai_result.get("intent", "general")
            # If AI detected it's vague, we might want to clarify
            if ai_result.get("is_vague") and not ai_result.get("is_urgent"):
                return ("clarify", ai_context)
            return (intent, ai_context)

    # Fallback to regex patterns
    message_lower = message.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                return (intent, ai_context)

    return ("general", ai_context)


# ============================================================================
# TOOL ROUTING
# ============================================================================
# Note: Natural language → DataPrime conversion is handled by
# coralogix.handle_search_logs() which now accepts natural language


def route_to_tool(
    intent: str,
    message: str,
    ai_context: dict = None,
    thread_context: list = None,
) -> dict:
    """Route a message to the appropriate MCP tool based on intent.

    AI-powered approach:
    - Uses AI context for service/env extraction when available
    - Uses thread context for follow-up awareness
    - CLEAR requests → execute immediately
    - VAGUE requests → AI-generated clarifying questions
    """
    from src.lib.cloudwatch import get_ecs_service_metrics, list_alarms
    from src.lib.code_search import search_knowledge_base
    from src.lib.coralogix import handle_get_recent_errors, handle_search_logs

    # Extract service/env from AI context if available
    service = ai_context.get("service") if ai_context else None
    env = ai_context.get("environment") if ai_context else None

    try:
        # Handle "clarify" intent from AI (vague requests)
        if intent == "clarify":
            print(f"[SlackBot] AI detected vague request, generating clarification")
            # Try AI-generated response with thread context
            ai_response = ai_generate_response(message, service, env, thread_context, intent)
            if ai_response:
                return {"response": ai_response}
            # Fallback to template
            return build_clarifying_response(message)

        # Legacy vague detection (fallback if AI not used)
        if is_vague_request(message) and not is_clear_request(message) and not ai_context:
            print(f"[SlackBot] Vague request detected, asking clarifying questions")
            return build_clarifying_response(message)

        if intent == "admin_toggle":
            # Toggle auto-reply on/off
            msg_lower = message.lower()
            if "on" in msg_lower or "enable" in msg_lower:
                SlackBot._auto_reply_enabled = True
                return {
                    "response": "✅ Auto-reply is now *enabled*. I'll respond to all messages in designated channels."
                }
            else:
                SlackBot._auto_reply_enabled = False
                return {"response": "🔇 Auto-reply is now *disabled*. I'll only respond when @mentioned."}

        if intent == "greeting":
            return {"response": CLIPPY_INTRO}

        elif intent == "alert_triage":
            # Extract service name if mentioned
            service_match = re.search(r"(cast-\w+|emvio-\w+|mrrobot-\w+)", message.lower())
            service = service_match.group(1) if service_match else "all"
            return handle_get_recent_errors(service, hours_back=4, limit=50)

        elif intent == "log_search":
            # Extract service and environment for context
            service_match = re.search(r"(cast-\w+|emvio-\w+|mrrobot-\w+)", message.lower())
            env_match = re.search(r"(prod|production|staging|sandbox|dev)", message.lower())

            service = service_match.group(1) if service_match else None
            env = env_match.group(1) if env_match else None

            # Build acknowledgment
            context_parts = []
            if service:
                context_parts.append(f"`{service}`")
            if env:
                context_parts.append(f"in *{env}*")
            context = " ".join(context_parts) if context_parts else "your query"

            print(f"[SlackBot] Log search query: '{message}' (service={service}, env={env})")
            result = handle_search_logs(message, hours_back=4, limit=50)

            # Add context to result
            if isinstance(result, dict):
                result["_context"] = context
                result["_is_troubleshooting"] = "issue" in message.lower() or "problem" in message.lower()
                print(f"[SlackBot] Log search result keys: {result.keys()}")
                if "logs" in result:
                    print(f"[SlackBot] Found {len(result['logs'])} logs")
            return result

        elif intent == "code_search":
            return search_knowledge_base(message, num_results=5)

        elif intent == "deploy_check":
            from src.lib.bitbucket import get_pipeline_status

            # Use AI to extract service name (handles variations like "emvio dashboard" -> "emvio-dashboard-app")
            entities = ai_extract_entities(message)
            repo = entities.get("service")

            # Fallback: try simple regex if AI didn't find it
            if not repo:
                service_match = re.search(r"([\w]+-[\w-]+)", message.lower())
                repo = service_match.group(1) if service_match else None

            if repo:
                return get_pipeline_status(repo, limit=5)
            else:
                return {"error": "Please specify a service name (e.g., 'recent deploys for emvio-dashboard-app')"}

        elif intent == "cloudwatch":
            # Check for alarm queries
            if "alarm" in message.lower():
                state = "ALARM" if "alarm" in message.lower() else None
                return list_alarms(state)
            # Default to ECS metrics for mrrobot-ai-core
            return get_ecs_service_metrics("mrrobot-ai-core", "mrrobot-mcp-server")

        elif intent == "access_request":
            return {
                "response": "For access requests, please create a ticket or contact IT directly. "
                "I can help you look up user information - try 'list atlassian users'."
            }

        elif intent == "pr_review":
            from src.lib.bitbucket import get_pr_details

            # Extract PR URL
            pr_match = re.search(r"bitbucket\.org/[^/]+/([^/]+)/pull-requests/(\d+)", message)
            if pr_match:
                repo, pr_id = pr_match.groups()
                pr_details = get_pr_details(repo, int(pr_id))
                pr_details["_intent"] = "pr_review"
                return pr_details
            return {"response": "Please provide the PR URL for me to review."}

        else:
            # General query - try code search
            return search_knowledge_base(message, num_results=3)

    except Exception as e:
        return {"error": str(e)}


def format_response(result: dict, intent: str) -> str:
    """Format a tool result for Slack display."""
    print(f"[SlackBot] Formatting response for intent: {intent}")
    print(f"[SlackBot] Result type: {type(result)}, keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

    if "error" in result:
        print(f"[SlackBot] Error in result: {result['error']}")
        return f"❌ Error: {result['error']}{CLIPPY_FOOTER}"

    if "response" in result:
        return result["response"] + CLIPPY_FOOTER

    # Format based on intent
    if intent == "alert_triage" and "errors_by_service" in result:
        errors_by_service = result.get("errors_by_service", {})
        total_errors = result.get("total_errors", 0)
        time_range = result.get("time_range", "")

        if not errors_by_service:
            return f"✅ No errors found in the last {time_range}."

        lines = [f"🚨 *Error Summary* ({total_errors} errors in {time_range}):"]
        lines.append("")

        # Sort by error count
        sorted_services = sorted(errors_by_service.items(), key=lambda x: len(x[1]), reverse=True)

        for service, errors in sorted_services[:5]:
            count = len(errors)
            lines.append(f"*`{service}`* - {count} errors")

            # Show first error message (cleaned up)
            if errors:
                first_error = errors[0].get("message", "")
                # Try to extract the key error message
                if "errorMessage" in first_error:
                    import re as re_mod

                    match = re_mod.search(r'"errorMessage":"([^"]+)"', first_error)
                    if match:
                        first_error = match.group(1)
                first_error = first_error[:120]
                lines.append(f"  └ _{first_error}..._")
            lines.append("")

        if len(sorted_services) > 5:
            lines.append(f"_...and {len(sorted_services) - 5} more services with errors_")

        return "\n".join(lines)

    if intent == "pr_review" and "pr_id" in result:
        pr = result
        lines = [
            f"📝 *PR #{pr['pr_id']}: {pr['title']}*",
            f"👤 Author: {pr['author']}",
            f"🌿 `{pr['source_branch']}` → `{pr['dest_branch']}`",
            f"📅 Created: {pr['created']}",
            "",
        ]

        # Files changed summary
        lines.append(f"📁 *{pr['total_files']} files changed* (+{pr['total_additions']} / -{pr['total_deletions']})")

        # Show file list (limited)
        for f in pr.get("files_changed", [])[:8]:
            status_emoji = {"added": "🟢", "removed": "🔴", "modified": "🟡"}.get(f["status"], "📄")
            lines.append(f"  {status_emoji} `{f['path']}` (+{f['lines_added']}/-{f['lines_removed']})")

        if pr["total_files"] > 8:
            lines.append(f"  _...and {pr['total_files'] - 8} more files_")

        # Approvals
        if pr.get("approvals"):
            lines.append("")
            lines.append("✅ *Approvals:*")
            for a in pr["approvals"]:
                lines.append(f"  • {a['user']} ({a['date']})")

        # Comments summary
        if pr.get("comments"):
            lines.append("")
            lines.append(f"💬 *{len(pr['comments'])} comment(s)*")

        # AI-powered PR assessment
        ai_review = ai_review_pr(pr)
        if ai_review:
            lines.append("")
            lines.append("🤖 *AI Assessment:*")
            lines.append(ai_review)

        # Action items
        lines.append("")
        lines.append(f"🔗 <{pr['url']}|View in Bitbucket>")

        return "\n".join(lines)

    if intent == "deploy_check" and "pipelines" in result:
        pipelines = result.get("pipelines", [])
        repo = result.get("repo", "")

        if not pipelines:
            return f"📦 No recent pipelines found for `{repo}`"

        lines = [f"📦 *Recent Deploys for `{repo}`:*"]
        for pipe in pipelines[:5]:
            state = pipe.get("result", pipe.get("state", ""))
            branch = pipe.get("branch", "")
            created = pipe.get("created", "")
            url = pipe.get("url", "")

            # Status emoji
            if state.upper() in ["SUCCESSFUL", "PASSED"]:
                emoji = "✅"
            elif state.upper() in ["FAILED", "ERROR"]:
                emoji = "❌"
            elif state.upper() in ["RUNNING", "PENDING", "IN_PROGRESS"]:
                emoji = "🔄"
            else:
                emoji = "⚪"

            if url:
                lines.append(f"{emoji} <{url}|#{pipe.get('build_number', '?')}> `{branch}` - {created}")
            else:
                lines.append(f"{emoji} #{pipe.get('build_number', '?')} `{branch}` - {created}")

        return "\n".join(lines)

    if intent == "code_search" and "results" in result:
        results = result.get("results", [])
        if not results:
            return "🔍 No results found."

        lines = ["🔍 *Code Search Results:*"]
        for r in results[:5]:
            repo = r.get("repo", "")
            file = r.get("file", "")
            score = r.get("score", 0)
            lines.append(f"• `{repo}/{file}` (score: {score:.2f})")
        return "\n".join(lines)

    if intent == "cloudwatch" and "alarms" in result:
        alarms = result.get("alarms", [])
        if not alarms:
            return "✅ No alarms found."

        lines = ["🔔 *CloudWatch Alarms:*"]
        for alarm in alarms[:10]:
            name = alarm.get("name", "")
            state = alarm.get("state", "")
            emoji = "🔴" if state == "ALARM" else "🟢" if state == "OK" else "⚪"
            lines.append(f"{emoji} `{name}`: {state}")
        return "\n".join(lines)

    if intent == "log_search" and "logs" in result:
        logs = result.get("logs", [])
        total = result.get("total_results", len(logs))
        query = result.get("query", "")
        dataprime = result.get("dataprime_query", "")
        context = result.get("_context", "")
        is_troubleshooting = result.get("_is_troubleshooting", False)
        print(f"[SlackBot] Formatting log_search: {len(logs)} logs, query: '{query}'")

        # Add context header for troubleshooting
        header = ""
        if is_troubleshooting and context:
            header = f"🔍 Looking into {context}...\n\n"

        if not logs:
            no_results = f"{header}📋 No logs found matching your query."
            no_results += f"\n\n_Searched: `{dataprime[:80]}`_"
            no_results += "\n\n💡 Try:\n• Expanding the time range\n• Checking a different environment\n• Searching for a specific error message"
            return no_results

        lines = [
            (
                f"{header}📋 *Found {total} logs* for {context}:"
                if context
                else f"📋 *Log Search Results* ({total} found):"
            )
        ]

        for i, log in enumerate(logs[:5]):
            print(f"[SlackBot] Log {i} type: {type(log)}, value: {str(log)[:100]}")
            if isinstance(log, dict):
                # Extract key fields
                msg = log.get("message", "")
                severity = log.get("severity", log.get("level", "INFO")).upper()
                service = log.get("logGroup", log.get("service", ""))
                ts = log.get("timestamp", "")

                # Parse timestamp (Unix ms or string)
                if isinstance(ts, (int, float)) and ts > 1000000000000:
                    ts_str = datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
                elif ts:
                    ts_str = str(ts)[11:19]  # Extract HH:MM:SS from ISO
                else:
                    ts_str = ""

                # Severity emoji
                if severity in ["ERROR", "FATAL", "CRITICAL"]:
                    emoji = "🔴"
                elif severity in ["WARN", "WARNING"]:
                    emoji = "⚠️"
                else:
                    emoji = "ℹ️"

                # Extract service name from logGroup
                service_name = service.split("/")[-1] if "/" in service else service
                service_name = service_name[:25] if service_name else ""

                # Clean up message - extract key error info
                if msg.startswith("{"):
                    try:
                        msg_json = json.loads(msg)
                        msg = msg_json.get("errorMessage", msg_json.get("message", msg))[:150]
                    except (json.JSONDecodeError, TypeError):
                        msg = msg[:150]
                else:
                    msg = msg[:150]

                lines.append(f"{emoji} `{ts_str}` *{service_name}*: {msg}")
            else:
                lines.append(f"ℹ️ {str(log)[:150]}")

        if total > 5:
            lines.append(f"\n_...and {total - 5} more results_")

        # AI-powered log analysis
        ai_summary = ai_summarize_logs(logs, query)
        if ai_summary:
            lines.append("")
            lines.append("🤖 *AI Analysis:*")
            lines.append(ai_summary)

        # Add follow-up suggestions for troubleshooting
        if is_troubleshooting:
            lines.append(TROUBLESHOOTING_FOLLOWUP)

        lines.append(f"\n_Query: `{dataprime[:80]}...`_")
        return "\n".join(lines)

    # For general intent with results, format nicely
    if "results" in result:
        results = result.get("results", [])
        if not results:
            return "🔍 No results found."

        lines = ["🔍 *Search Results:*"]
        for r in results[:5]:
            repo = r.get("repo", "")
            file = r.get("file", "")
            url = r.get("bitbucket_url", "")
            if url:
                lines.append(f"• <{url}|{repo}/{file}>")
            else:
                lines.append(f"• `{repo}/{file}`")
        return "\n".join(lines)

    # Default: return JSON preview
    import json

    return f"```{json.dumps(result, indent=2, default=str)[:1500]}```{CLIPPY_FOOTER}"


# ============================================================================
# SLACK BOT
# ============================================================================


class SlackBot:
    """Slack bot that routes messages to MCP tools.

    Auto-reply behavior:
    - Always responds to @mentions in any channel
    - Auto-replies to all new messages (once per thread) in AUTO_REPLY_CHANNELS (when enabled)
    - Configure via SLACK_AUTO_REPLY_CHANNELS env var (comma-separated channel IDs)
    - Toggle auto-reply via "@Clippy-ai auto-reply on/off"
    """

    # Channels where bot auto-replies to all messages (not just mentions)
    # Loaded from Secrets Manager or environment variable
    # Can be toggled at runtime via "@Clippy-ai auto-reply on/off"
    _auto_reply_enabled = False  # Global toggle - disabled by default, use @mention instead

    # Default channel for devops + any configured via secrets/env
    AUTO_REPLY_CHANNELS = {"C0A3RJA9LSJ"}  # Will be updated in __init__

    def __init__(self, bot_token: str = None, app_token: str = None):
        """Initialize the Slack bot.

        Args:
            bot_token: Slack bot token (xoxb-...) or fetched from secrets
            app_token: Slack app token (xapp-...) or fetched from secrets
        """
        self.bot_token = bot_token or get_secret("SLACK_BOT_TOKEN")
        self.app_token = app_token or get_secret("SLACK_APP_TOKEN")
        self.app = None
        self.handler = None

        # Load additional auto-reply channels from secrets/env
        channels_str = get_secret("SLACK_AUTO_REPLY_CHANNELS") or ""
        if not channels_str:
            channels_str = os.environ.get("SLACK_AUTO_REPLY_CHANNELS", "")
        if channels_str:
            SlackBot.AUTO_REPLY_CHANNELS.update(filter(None, channels_str.split(",")))
        self._thread = None
        self._responded_threads = set()  # Track threads we've already responded to
        self._bot_user_id = None  # Will be set on startup

    def is_configured(self) -> bool:
        """Check if Slack tokens are configured."""
        return bool(self.bot_token and self.app_token)

    def _setup_app(self):
        """Set up the Slack Bolt app with event handlers."""
        global _slack_client
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        self.app = App(token=self.bot_token)

        # Set global slack client for error alerting
        _slack_client = self.app.client

        @self.app.event("app_mention")
        def handle_mention(event, say, client):
            """Handle @mentions of the bot - uses Claude Tool Use."""
            text = event.get("text", "")
            channel = event["channel"]
            thread_ts = event.get("thread_ts") or event["ts"]
            user = event.get("user", "")

            # Remove bot mention from text
            text = re.sub(r"<@\w+>", "", text).strip()

            print(f"[Clippy] Mention from {user}: {text[:100]}")

            # Handle empty message
            if not text:
                say(
                    "👋 Hi! I'm Clippy, your DevOps assistant. Try:\n"
                    "• `search logs for errors in prod`\n"
                    "• `check recent deploys for emvio-dashboard-app`\n"
                    "• `find CSP configuration in codebase`\n"
                    "• `list CloudWatch alarms`",
                    thread_ts=thread_ts,
                )
                return

            # Acknowledge immediately with context-aware message
            ack_msg = _get_acknowledgment(text)
            say(ack_msg, thread_ts=thread_ts)

            # Fetch thread context for follow-up awareness
            thread_context = get_thread_context(client, channel, thread_ts)
            if thread_context:
                print(f"[Clippy] Thread context: {len(thread_context)} messages")

            # Use Claude Tool Use - Claude decides what to do
            result = invoke_claude_with_tools(text, thread_context)

            print(f"[Clippy] Tool used: {result.get('tool_used')}")

            # Format response with footer, convert markdown, and redact any secrets
            response = result.get("response", "I'm not sure how to help with that.")
            response = _convert_to_slack_markdown(response)  # Convert **bold** to *bold*
            response = _redact_secrets(response)
            # Only add footer if not already present (avoid duplicates)
            if "Clippy is a work in progress" not in response:
                response += CLIPPY_FOOTER

            # Reply in thread
            say(response, thread_ts=thread_ts)

        @self.app.command("/devops")
        def handle_command(ack, respond, command):
            """Handle /devops slash command - uses Claude Tool Use."""
            ack()
            text = command.get("text", "")
            user = command.get("user_id", "")

            print(f"[Clippy] Command from {user}: {text[:100]}")

            # Use Claude Tool Use
            result = invoke_claude_with_tools(text)
            response = result.get("response", "I'm not sure how to help with that.")
            response = _convert_to_slack_markdown(response)  # Convert **bold** to *bold*
            response = _redact_secrets(response)
            # Only add footer if not already present (avoid duplicates)
            if "Clippy is a work in progress" not in response:
                response += CLIPPY_FOOTER

            respond(response)

        @self.app.command("/clippy-help")
        def handle_help_command(ack, respond, command):
            """Handle /clippy-help slash command - shows Clippy's capabilities."""
            ack()

            help_text = """*:paperclip: Clippy Capabilities*

*Logs & Troubleshooting*
• `@Clippy check logs for errors in [service]` - Search Coralogix logs
• `@Clippy what's broken?` - Get recent errors across services
• `@Clippy investigate [service] in prod` - Full automated investigation

*Code Search*
• `@Clippy how does authentication work?` - Semantic code search across 254 repos
• `@Clippy find CSP configuration` - Find specific implementations

*Deployments & Pipelines*
• `@Clippy pipeline status for [repo]` - Recent builds/deploys
• `@Clippy why did build 123 fail in [repo]?` - Pipeline failure details

*Pull Requests*
• `@Clippy show open PRs in [repo]` - List open pull requests
• `@Clippy [paste Bitbucket PR URL]` - Get PR details and diff summary

*Jira Tickets*
• `@Clippy show me open CVE tickets` - Security vulnerability tickets
• `@Clippy tell me about DEVOPS-123` - Get ticket details
• `@Clippy find tickets with PCI label` - Search by label

*PagerDuty Incidents*
• `@Clippy show me active incidents` - Currently triggered/acknowledged
• `@Clippy incidents this week` - Recent incident history
• `@Clippy investigate incident PXXXXXX` - Full details + related logs

*AWS & CloudWatch*
• `@Clippy list alarms in ALARM state` - Check CloudWatch alarms
• `@Clippy search CloudWatch logs for [service]` - AWS log search
• `@Clippy check ECS metrics` - CPU/memory usage

*DevOps History*
• `@Clippy have we seen 504 errors before?` - Search past Slack conversations

*Example Queries:*
```
@Clippy cast-core is returning 504s in prod
@Clippy why did the emvio-dashboard-app deploy fail?
@Clippy show me CVE tickets assigned to me
@Clippy what changed in cast-core recently?
```

_Tip: Be specific with service names and environments for best results!_"""

            respond(help_text)

        @self.app.event("message")
        def handle_message(event, say, client):
            """Handle all messages - auto-reply once per thread in designated channels.

            Uses Claude Tool Use for AI-powered responses.
            Only responds to new parent messages, not thread replies (use @mention for follow-ups).
            """
            channel = event.get("channel", "")
            text = event.get("text", "")[:200] if event.get("text") else ""
            subtype = event.get("subtype", "")

            # Skip bot messages and message edits
            if subtype in ["bot_message", "message_changed", "message_deleted"]:
                return

            # Skip thread replies - only auto-reply to parent messages
            # (Use @mention for follow-up questions in threads - it has full context)
            if event.get("thread_ts") and event.get("thread_ts") != event.get("ts"):
                return

            text = event.get("text", "")
            ts = event.get("ts", "")
            user = event.get("user", "")

            # Get bot user ID if we don't have it
            if not self._bot_user_id:
                try:
                    auth_response = client.auth_test()
                    self._bot_user_id = auth_response.get("user_id")
                except Exception:
                    pass

            # Skip messages from the bot itself
            if user == self._bot_user_id:
                return

            # Skip if message mentions the bot (handled by app_mention)
            if self._bot_user_id and f"<@{self._bot_user_id}>" in text:
                return

            # Check if auto-reply is enabled globally
            if not SlackBot._auto_reply_enabled:
                return

            # Only auto-reply in designated channels
            if channel not in SlackBot.AUTO_REPLY_CHANNELS:
                return

            # Skip if we've already responded to this thread
            thread_key = f"{channel}:{ts}"
            if thread_key in self._responded_threads:
                return

            # Mark thread as responded
            self._responded_threads.add(thread_key)

            # Clean up old thread keys (keep last 1000)
            if len(self._responded_threads) > 1000:
                to_remove = list(self._responded_threads)[:500]
                for key in to_remove:
                    self._responded_threads.discard(key)

            print(f"[Clippy] Auto-reply in {channel}: {text[:100]}")

            # Acknowledge with context-aware message
            ack_msg = _get_acknowledgment(text)
            say(ack_msg, thread_ts=ts)

            # Use Claude Tool Use (no thread context for initial auto-reply)
            result = invoke_claude_with_tools(text)
            response = result.get("response", "I'm not sure how to help with that.")
            response = _redact_secrets(response)
            # Only add footer if not already present (avoid duplicates)
            if "Clippy is a work in progress" not in response:
                response += CLIPPY_FOOTER

            say(response, thread_ts=ts)

        self.handler = SocketModeHandler(self.app, self.app_token)

    def start(self, blocking: bool = False):
        """Start the Slack bot.

        Args:
            blocking: If True, blocks the current thread. If False, runs in background.
        """
        if not self.is_configured():
            print("[SlackBot] Slack tokens not configured, skipping bot startup")
            return

        try:
            from slack_bolt import App  # noqa: F401
        except ImportError:
            print("[SlackBot] slack-bolt not installed, skipping bot startup")
            return

        self._setup_app()

        if blocking:
            print("[SlackBot] Starting in foreground...")
            self.handler.start()
        else:
            print("[SlackBot] Starting in background thread...")
            self._thread = threading.Thread(target=self.handler.start, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop the Slack bot."""
        if self.handler:
            self.handler.close()


# ============================================================================
# LOCAL TESTING (without Slack connection)
# ============================================================================


def test_intent_classification():
    """Test intent classification with sample messages."""
    test_messages = [
        ("check errors in cast-core prod", "alert_triage"),
        ("approve this PR https://bitbucket.org/mrrobot-labs/cast-core/pull-requests/123", "pr_review"),
        ("where is CSP configured?", "code_search"),
        ("search logs for timeout errors", "log_search"),
        ("create sftp user for john", "access_request"),
        ("show cloudwatch alarms", "cloudwatch"),
        ("what's the weather?", "general"),
    ]

    print("\n=== Intent Classification Tests ===\n")
    all_passed = True

    for message, expected in test_messages:
        result, _ = classify_intent(message, use_ai=False)  # Use regex for tests
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"{status} '{message[:50]}...' -> {result} (expected: {expected})")

    return all_passed


def test_tool_routing():
    """Test tool routing with sample intents."""
    print("\n=== Tool Routing Tests ===\n")

    test_cases = [
        ("alert_triage", "check errors in cast-core"),
        ("code_search", "where is authentication implemented?"),
        ("cloudwatch", "show me ECS metrics"),
    ]

    for intent, message in test_cases:
        print(f"Testing intent: {intent}")
        print(f"  Message: {message}")
        try:
            result = route_to_tool(intent, message)
            if "error" in result:
                print(f"  ❌ Error: {result['error']}")
            else:
                print(f"  ✅ Got response with keys: {list(result.keys())}")
        except Exception as e:
            print(f"  ❌ Exception: {e}")
        print()


def test_local():
    """Run local tests without Slack connection."""
    print("=" * 60)
    print("SLACK BOT LOCAL TESTING")
    print("=" * 60)

    # Test intent classification
    classification_ok = test_intent_classification()

    # Test tool routing (requires AWS credentials)
    print("\nSkipping tool routing tests (requires AWS credentials)")
    # test_tool_routing()

    print("\n" + "=" * 60)
    if classification_ok:
        print("✅ All intent classification tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Slack Bot for DevOps")
    parser.add_argument("--test", action="store_true", help="Run local tests")
    parser.add_argument("--start", action="store_true", help="Start the bot (requires tokens)")
    args = parser.parse_args()

    if args.test:
        test_local()
    elif args.start:
        bot = SlackBot()
        if bot.is_configured():
            print("Starting Slack bot...")
            bot.start(blocking=True)
        else:
            print("Slack tokens not configured. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN.")
    else:
        parser.print_help()
