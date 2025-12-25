"""Clippy Tool Definitions for Claude Tool Use.

This module defines all available tools for the Clippy Slack bot.
Tools are organized by category and include:
- Logging & Monitoring (Coralogix)
- Deployments & CI/CD (Bitbucket Pipelines, PRs)
- Issue Tracking (Jira, PagerDuty)
- Infrastructure (AWS CLI)
- Code Search (Knowledge Base)
"""

from typing import Any

# =============================================================================
# TOOL BUILDERS - Helper functions for consistent tool definitions
# =============================================================================


def _tool(
    name: str,
    description: str,
    properties: dict = None,
    required: list = None,
) -> dict:
    """Build a tool definition with consistent structure."""
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


def _param(
    description: str,
    param_type: str = "string",
    default: Any = None,
    enum: list = None,
) -> dict:
    """Build a parameter definition."""
    param = {"type": param_type, "description": description}
    if default is not None:
        param["default"] = default
    if enum:
        param["enum"] = enum
    return param


# =============================================================================
# LOGGING & MONITORING TOOLS
# =============================================================================

LOGGING_TOOLS = [
    _tool(
        name="search_logs",
        description="""Search application logs in Coralogix. PRIMARY tool for all log searches.

CRITICAL: Always include environment (prod/staging/dev) in query!

Examples:
- "errors in cast-core prod" -> searches prod cast-core for errors
- "504 timeout emvio-dashboard staging" -> searches staging for 504s
- "ECONNREFUSED payment-service prod last 2 hours" -> connection errors
- "authentication failed mrrobot-auth prod" -> auth failures

BAD (missing environment):
- "errors in cast-core" -> will ask user which environment

Use hours_back to control time range (default: 4 hours).""",
        properties={
            "query": _param("Search with service AND environment (e.g., 'errors in cast-core prod')"),
            "hours_back": _param("Hours to search back", "integer", default=4),
            "limit": _param("Max results", "integer", default=50),
        },
        required=["query"],
    ),
    _tool(
        name="get_recent_errors",
        description="""Get recent errors grouped by service. Use for:
- "What's broken right now?"
- Alert triage / health overview
- "Any errors in the last hour?"

Returns error counts per service with sample messages.
Optionally filter by service name and environment.""",
        properties={
            "service": _param("Service name (e.g., 'cast-core') or 'all' for overview"),
            "hours_back": _param("Hours to check", "integer", default=4),
            "environment": _param("Filter by environment", enum=["prod", "staging", "dev", "all"]),
        },
    ),
]

# =============================================================================
# DEPLOYMENT & CI/CD TOOLS
# =============================================================================

DEPLOYMENT_TOOLS = [
    _tool(
        name="get_pipeline_status",
        description="""Check recent CI/CD pipeline/build status for a repository.

Use when:
- "Did the deploy go through?"
- "Any failed builds?"
- Correlating errors with recent deploys

Example workflow:
1. User reports errors starting 30 min ago
2. Check get_pipeline_status -> see deploy 35 min ago
3. Likely cause: recent deploy

NOTE: Shows build status, not deployment status. A passed build means tests passed.""",
        properties={
            "repo": _param("Repository name (e.g., 'emvio-dashboard-app', 'cast-core-service')"),
            "limit": _param("Number of recent pipelines", "integer", default=5),
        },
        required=["repo"],
    ),
    _tool(
        name="get_pipeline_details",
        description="""Get detailed info about a specific pipeline/build including failure logs.

Use when:
- User shares a pipeline URL
- "Why did build #123 fail?"
- Need to see actual error from failed build

Extract from URL: bitbucket.org/mrrobot-labs/REPO/pipelines/results/NUMBER""",
        properties={
            "repo": _param("Repository name"),
            "pipeline_id": _param("Pipeline/build number", "integer"),
        },
        required=["repo", "pipeline_id"],
    ),
    _tool(
        name="list_open_prs",
        description="""List open pull requests for a repository.

Use for:
- "What PRs need review?"
- "Any open PRs for cast-core?"
- Getting PR overview before diving into details""",
        properties={
            "repo": _param("Repository name (e.g., 'cast-core-service')"),
            "limit": _param("Max PRs to return", "integer", default=5),
        },
        required=["repo"],
    ),
    _tool(
        name="get_pr_details",
        description="""Get PR details including diff, comments, reviewers, status.

ALWAYS use when given a Bitbucket PR URL!

URL format: bitbucket.org/mrrobot-labs/REPO/pull-requests/ID
Example: bitbucket.org/mrrobot-labs/cast-core-service/pull-requests/456
-> repo="cast-core-service", pr_id=456""",
        properties={
            "repo": _param("Repository name from URL"),
            "pr_id": _param("PR ID number from URL", "integer"),
        },
        required=["repo", "pr_id"],
    ),
]

# =============================================================================
# JIRA TOOLS
# =============================================================================

JIRA_TOOLS = [
    _tool(
        name="jira_search",
        description="Search Jira tickets. Supports natural language ('CVE tickets', 'open bugs', 'my tickets') or direct keys ('DEVOPS-123').",
        properties={
            "query": _param("Search query or ticket key"),
            "max_results": _param("Max tickets", "integer", default=20),
        },
        required=["query"],
    ),
    _tool(
        name="jira_cve_tickets",
        description="Get open CVE/security vulnerability tickets.",
        properties={
            "max_results": _param("Max tickets", "integer", default=50),
        },
    ),
    _tool(
        name="jira_get_ticket",
        description="Get detailed info about a specific Jira ticket including description and comments.",
        properties={
            "issue_key": _param("Ticket key (e.g., 'DEVOPS-123')"),
        },
        required=["issue_key"],
    ),
]

# =============================================================================
# CONFLUENCE TOOLS
# =============================================================================

CONFLUENCE_TOOLS = [
    _tool(
        name="search_confluence",
        description="""Search Confluence documentation for HR policies, runbooks, architecture docs, onboarding guides, and company info.
Examples: 'PTO policy', 'deployment runbook', 'onboarding checklist', 'expense report process'""",
        properties={
            "query": _param("Natural language search query"),
            "space_key": _param("Limit to space (e.g., 'HR', 'DEV', 'OPS') - optional"),
            "limit": _param("Max results", "integer", default=10),
        },
        required=["query"],
    ),
    _tool(
        name="get_confluence_page",
        description="Get full content of a specific Confluence page by ID.",
        properties={
            "page_id": _param("Confluence page ID"),
        },
        required=["page_id"],
    ),
    _tool(
        name="list_confluence_spaces",
        description="List all available Confluence spaces. Use to discover what documentation exists.",
    ),
    _tool(
        name="recent_confluence_updates",
        description="Get recently updated Confluence pages. Use for 'what docs changed recently?'",
        properties={
            "space_key": _param("Limit to space (optional)"),
            "limit": _param("Max results", "integer", default=15),
        },
    ),
]

# =============================================================================
# PAGERDUTY TOOLS
# =============================================================================

PAGERDUTY_TOOLS = [
    _tool(
        name="pagerduty_active_incidents",
        description="Get currently active incidents (triggered/acknowledged). Use for 'what's on fire?', active alerts, on-call status.",
    ),
    _tool(
        name="pagerduty_recent_incidents",
        description="Get incidents from past N days (all statuses). Use for 'incidents this week', incident history.",
        properties={
            "days": _param("Days to look back", "integer", default=7),
        },
    ),
    _tool(
        name="pagerduty_incident_details",
        description="Get full incident details including notes and timeline.",
        properties={
            "incident_id": _param("Incident ID (e.g., 'PXXXXXX') or number"),
        },
        required=["incident_id"],
    ),
    _tool(
        name="pagerduty_investigate",
        description="Investigate an incident - gets details AND checks related logs/code automatically.",
        properties={
            "incident_id": _param("Incident ID to investigate"),
        },
        required=["incident_id"],
    ),
]

# =============================================================================
# INFRASTRUCTURE & CODE TOOLS
# =============================================================================

INFRASTRUCTURE_TOOLS = [
    _tool(
        name="aws_cli",
        description="""Run read-only AWS CLI commands. DO NOT include 'aws' prefix.

Examples:
- "elbv2 describe-load-balancers" - list load balancers
- "ecs describe-services --cluster mrrobot-ai-core --services mrrobot-mcp-server" - ECS service info
- "ec2 describe-security-groups --group-ids sg-xxx" - security group rules
- "lambda get-function --function-name my-function" - Lambda config

BLOCKED commands: delete, terminate, create, put, get-secret-value""",
        properties={
            "command": _param("AWS CLI command without 'aws' prefix"),
            "region": _param("AWS region", default="us-east-1"),
        },
        required=["command"],
    ),
    _tool(
        name="search_code",
        description="""Semantic search across 254 MrRobot repositories.

Use for:
- "How does authentication work?" -> search "authentication flow"
- "Where is CORS configured?" -> search "CORS configuration"
- "Find webhook handling code" -> search "webhook handler"

Returns file paths, code snippets, and repo names.
Follow up with get_file_content for full files.""",
        properties={
            "query": _param("What to search (e.g., 'JWT validation', 'database connection')"),
            "num_results": _param("Number of results", "integer", default=5),
        },
        required=["query"],
    ),
    _tool(
        name="get_service_info",
        description="""Look up service metadata from the registry (129 services).

Returns:
- Type: frontend/backend/library
- Tech stack: Node.js, Lambda, React, etc.
- Full name and aliases
- Troubleshooting suggestions

Use FIRST when unsure about a service to know if it's frontend (check deploys first) or backend (check logs first).""",
        properties={
            "service_name": _param("Service name or alias (e.g., 'cast', 'dashboard', 'emvio-gateway')"),
        },
        required=["service_name"],
    ),
    _tool(
        name="search_devops_history",
        description="""Search past DevOps Slack conversations for similar issues.

PROACTIVELY USE when troubleshooting! Examples:
- "504 cast-core" - find past 504 discussions
- "SFTP connection" - find SFTP setup help
- "deployment rollback" - find rollback procedures

Returns: past conversations with solutions that worked.""",
        properties={
            "query": _param("Error message, service name, or issue description"),
        },
        required=["query"],
    ),
]

# =============================================================================
# INVESTIGATION TOOLS
# =============================================================================

INVESTIGATION_TOOLS = [
    _tool(
        name="investigate_issue",
        description="""Run thorough multi-step autonomous investigation.

Use when:
- "Cast-core is broken in prod"
- "Help debug this issue"
- "Why is X not working?"
- Complex issues needing multiple tool calls

The agent will automatically:
1. Search logs for errors
2. Check recent deploys
3. Correlate timing
4. Report findings with recommendations

ALWAYS specify environment to avoid searching wrong env.""",
        properties={
            "service": _param("Service to investigate (e.g., 'cast-core', 'emvio-dashboard')"),
            "environment": _param(
                "REQUIRED: prod, staging, dev, or sandbox", enum=["prod", "staging", "dev", "sandbox"]
            ),
            "description": _param("What the user is seeing / when it started"),
        },
        required=["service", "environment"],
    ),
]

# =============================================================================
# META TOOLS
# =============================================================================

META_TOOLS = [
    _tool(
        name="respond_directly",
        description="ONLY for greetings ('hi', 'thanks') or 'what can you do'. For ANY issue/error - investigate first, THEN ask questions.",
        properties={
            "message": _param("Simple greeting or capability explanation"),
        },
        required=["message"],
    ),
]

# =============================================================================
# COMBINED TOOLS LIST
# =============================================================================

CLIPPY_TOOLS = (
    LOGGING_TOOLS
    + DEPLOYMENT_TOOLS
    + JIRA_TOOLS
    + CONFLUENCE_TOOLS
    + PAGERDUTY_TOOLS
    + INFRASTRUCTURE_TOOLS
    + INVESTIGATION_TOOLS
    + META_TOOLS
)

# Tool count for reference
TOOL_COUNT = len(CLIPPY_TOOLS)


def get_tools_by_category() -> dict:
    """Get tools organized by category for documentation."""
    return {
        "Logging & Monitoring": LOGGING_TOOLS,
        "Deployments & CI/CD": DEPLOYMENT_TOOLS,
        "Jira": JIRA_TOOLS,
        "Confluence": CONFLUENCE_TOOLS,
        "PagerDuty": PAGERDUTY_TOOLS,
        "Infrastructure & Code": INFRASTRUCTURE_TOOLS,
        "Investigation": INVESTIGATION_TOOLS,
        "Meta": META_TOOLS,
    }


def get_tool_names() -> list:
    """Get list of all tool names."""
    return [tool["name"] for tool in CLIPPY_TOOLS]
