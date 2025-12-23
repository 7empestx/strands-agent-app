"""Clippy Tool Definitions for Claude Tool Use.

This module defines all available tools for the Clippy Slack bot.
Tools are organized by category and include:
- Logging & Monitoring (Coralogix, CloudWatch)
- Deployments & CI/CD (Bitbucket Pipelines, PRs)
- Issue Tracking (Jira, PagerDuty)
- Infrastructure (AWS CLI, ECS)
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
        description="Search application logs in Coralogix. Use for troubleshooting errors, investigating issues, or finding specific log patterns.",
        properties={
            "query": _param("Natural language search (e.g., 'errors in cast-core prod', 'timeout issues')"),
            "hours_back": _param("Hours to search back", "integer", default=4),
            "limit": _param("Max results", "integer", default=50),
        },
        required=["query"],
    ),
    _tool(
        name="get_recent_errors",
        description="Get recent errors across services. Use for 'what's broken?', alert triage, or health checks.",
        properties={
            "service": _param("Service name (e.g., 'cast-core') or 'all'"),
            "hours_back": _param("Hours to check", "integer", default=4),
        },
    ),
    _tool(
        name="search_cloudwatch_logs",
        description="Search AWS CloudWatch logs. Use when user says 'check CloudWatch' or for Lambda logs.",
        properties={
            "service": _param("Service name (e.g., 'mrrobot-cast-core-prod')"),
            "query": _param("Search term (e.g., '504', 'error', 'timeout')"),
            "hours_back": _param("Hours to search", "integer", default=4),
        },
        required=["service"],
    ),
    _tool(
        name="list_alarms",
        description="List CloudWatch alarms. Use for monitoring/alerting questions.",
        properties={
            "state": _param("Filter: 'ALARM', 'OK', or 'INSUFFICIENT_DATA'", enum=["ALARM", "OK", "INSUFFICIENT_DATA"]),
        },
    ),
    _tool(
        name="get_ecs_metrics",
        description="Get ECS service CPU/memory metrics.",
        properties={
            "cluster": _param("ECS cluster name", default="mrrobot-ai-core"),
            "service": _param("ECS service name", default="mrrobot-mcp-server"),
        },
    ),
]

# =============================================================================
# DEPLOYMENT & CI/CD TOOLS
# =============================================================================

DEPLOYMENT_TOOLS = [
    _tool(
        name="get_pipeline_status",
        description="Check recent deployments/pipelines. Use for 'what changed?', 'did it deploy?', build status.",
        properties={
            "repo": _param("Repository name (e.g., 'emvio-dashboard-app', 'cast-core')"),
            "limit": _param("Number of pipelines", "integer", default=5),
        },
        required=["repo"],
    ),
    _tool(
        name="get_pipeline_details",
        description="Get details about a specific build including failure logs. Use when user shares pipeline URL or asks why build failed.",
        properties={
            "repo": _param("Repository name"),
            "pipeline_id": _param("Pipeline/build number", "integer"),
        },
        required=["repo", "pipeline_id"],
    ),
    _tool(
        name="list_open_prs",
        description="List open pull requests for a repository.",
        properties={
            "repo": _param("Repository name (e.g., 'cast-core')"),
            "limit": _param("Max PRs to return", "integer", default=5),
        },
        required=["repo"],
    ),
    _tool(
        name="get_pr_details",
        description="Get PR details. ALWAYS use when given a Bitbucket PR URL. Extract repo and pr_id from: bitbucket.org/mrrobot-labs/REPO/pull-requests/ID",
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
        description="""Run read-only AWS CLI commands. Examples:
- Load balancers: "elbv2 describe-load-balancers"
- ECS: "ecs describe-services --cluster mrrobot-ai-core --services my-service"
- Security groups: "ec2 describe-security-groups --group-ids sg-xxx"
DO NOT include 'aws' prefix.""",
        properties={
            "command": _param("AWS CLI command without 'aws' prefix"),
            "region": _param("AWS region", default="us-east-1"),
        },
        required=["command"],
    ),
    _tool(
        name="search_code",
        description="Semantic search across 254 MrRobot repos. Use for finding implementations, configs, understanding code.",
        properties={
            "query": _param("What to search (e.g., 'CSP configuration', 'auth middleware')"),
            "num_results": _param("Number of results", "integer", default=5),
        },
        required=["query"],
    ),
    _tool(
        name="get_service_info",
        description="Look up service type (frontend/backend), tech stack, dependencies. Use FIRST when unsure about a service.",
        properties={
            "service_name": _param("Service/repo name (e.g., 'emvio-dashboard-app')"),
        },
        required=["service_name"],
    ),
    _tool(
        name="search_devops_history",
        description="""Search past DevOps Slack conversations for similar issues/solutions.
PROACTIVELY USE when troubleshooting to find if we've seen this before.
Examples: "504 cast", "SFTP setup", "deployment failed".""",
        properties={
            "query": _param("Search terms (error types, service names, issues)"),
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
        description="Run thorough multi-step investigation. Use for 'something is broken', 'help debug', 'why is X not working'. Checks logs, deploys, alarms automatically.",
        properties={
            "service": _param("Service to investigate (e.g., 'cast-core')"),
            "environment": _param("Environment", enum=["prod", "staging", "dev", "sandbox"]),
            "description": _param("What the user is seeing / when it started"),
        },
        required=["service"],
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
        "PagerDuty": PAGERDUTY_TOOLS,
        "Infrastructure & Code": INFRASTRUCTURE_TOOLS,
        "Investigation": INVESTIGATION_TOOLS,
        "Meta": META_TOOLS,
    }


def get_tool_names() -> list:
    """Get list of all tool names."""
    return [tool["name"] for tool in CLIPPY_TOOLS]
