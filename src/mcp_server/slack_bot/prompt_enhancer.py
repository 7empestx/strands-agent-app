"""Prompt enhancement for Clippy Slack bot.

Provides AI-powered and rule-based message enhancement to add context
before sending to Claude for tool use.
"""

import json
import re
from datetime import datetime, timedelta

from src.lib.config_loader import get_env_mappings, get_service_registry
from src.lib.error_patterns import get_investigation_context
from src.mcp_server.slack_bot.bedrock_client import get_bedrock_client


def _build_service_context(registry: dict, limit: int = 30) -> str:
    """Build a service context string from the registry for the AI prompt.

    Prioritizes services with more aliases (more commonly referenced).

    Args:
        registry: Service registry dict
        limit: Max number of services to include

    Returns:
        Formatted string of services and aliases for the AI
    """
    if not registry:
        return "- (service registry unavailable)"

    # Sort by number of aliases (more aliases = more commonly referenced)
    services = []
    for key, info in registry.items():
        aliases = info.get("aliases", [])
        full_name = info.get("full_name", key)
        svc_type = info.get("type", "")

        # Prioritize services with more aliases
        services.append(
            {
                "key": key,
                "full_name": full_name,
                "aliases": aliases,
                "type": svc_type,
                "priority": len(aliases),
            }
        )

    # Sort by priority (more aliases first), then alphabetically
    services.sort(key=lambda x: (-x["priority"], x["key"]))

    # Build context string
    lines = []
    for svc in services[:limit]:
        aliases_str = ", ".join(svc["aliases"][:5]) if svc["aliases"] else ""
        if aliases_str:
            lines.append(f"- {svc['full_name']} (aliases: {aliases_str})")
        else:
            lines.append(f"- {svc['full_name']}")

    return "\n".join(lines)


def _detect_suspicious_request(message: str) -> dict | None:
    """Detect potentially suspicious requests that need security escalation.

    Returns dict with warning info if suspicious, None otherwise.
    """
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
    # Check for suspicious requests first
    suspicious = _detect_suspicious_request(message)
    if suspicious:
        print(f"[Clippy] SECURITY: Suspicious request detected - {suspicious['category']}")
        return f"{message}\n\n---\n{suspicious['warning']}"

    # Get current date context for the AI
    now = datetime.now()
    date_context = f"Today is {now.strftime('%A, %B %d, %Y')}. Current time: {now.strftime('%H:%M')}."

    # Get service registry for context (top 30 most common services)
    service_registry = get_service_registry()
    service_context = _build_service_context(service_registry, limit=30)

    # Build the extraction prompt
    extraction_prompt = f"""Extract structured information from this DevOps Slack message.

{date_context}

Known services (with aliases):
{service_context}

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
    Also adds error pattern hints if applicable.
    """
    # Try AI-powered enhancement first
    enhanced = enhance_prompt_with_ai(message)

    # Add error pattern context if we detect a known error type
    error_context = get_investigation_context(message)
    if error_context:
        enhanced += error_context
        print(f"[Clippy] Added error pattern context")

    if enhanced != message:
        return enhanced

    # Fallback: Simple rule-based enhancement
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
