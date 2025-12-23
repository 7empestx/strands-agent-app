"""Strands-based Investigation Agent.

A multi-step autonomous agent that thoroughly investigates DevOps issues.
Called by Claude Tool Use when complex investigation is needed.

Uses Strands Agent framework for autonomous multi-tool orchestration.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands.models import BedrockModel

from src.lib.bitbucket import get_pipeline_status
from src.lib.cloudwatch import get_ecs_service_metrics, list_alarms

# Import our existing MCP tools
from src.lib.coralogix import handle_get_recent_errors, handle_search_logs

# ============================================================================
# STRANDS TOOLS - Wrappers around our MCP tools
# ============================================================================


@tool
def search_logs(query: str, hours_back: int = 4) -> dict:
    """Search application logs for errors, patterns, or specific messages.

    Args:
        query: Natural language search query (e.g., 'errors in emvio-dashboard staging')
        hours_back: How many hours back to search (default: 4)

    Returns:
        dict with logs, total_results, and dataprime_query used
    """
    return handle_search_logs(query, hours_back=hours_back, limit=50)


@tool
def check_recent_deploys(service: str, limit: int = 5) -> dict:
    """Check recent deployments/pipelines for a service.

    Args:
        service: Service/repository name (e.g., 'emvio-dashboard-app', 'cast-core')
        limit: Number of recent deploys to show

    Returns:
        dict with pipelines list containing status, branch, time, etc.
    """
    return get_pipeline_status(service, limit=limit)


@tool
def get_error_summary(service: str = "all", hours_back: int = 4, environment: str = "all") -> dict:
    """Get a summary of recent errors across services.

    Args:
        service: Service name to filter, or 'all' for all services
        hours_back: How many hours back to check
        environment: Environment to check - 'prod', 'staging', 'dev', or 'all'

    Returns:
        dict with errors_by_service breakdown
    """
    return handle_get_recent_errors(service, hours_back=hours_back, limit=50, environment=environment)


@tool
def check_alarms(state: str = None) -> dict:
    """Check CloudWatch alarms for any issues.

    Args:
        state: Filter by state - 'ALARM', 'OK', or None for all

    Returns:
        dict with alarms list
    """
    return list_alarms(state_value=state)


@tool
def check_ecs_health(cluster: str = "mrrobot-ai-core", service: str = "mrrobot-mcp-server") -> dict:
    """Check ECS service health metrics (CPU, memory).

    Args:
        cluster: ECS cluster name
        service: ECS service name

    Returns:
        dict with CPU and memory metrics
    """
    return get_ecs_service_metrics(cluster, service)


# ============================================================================
# INVESTIGATION AGENT
# ============================================================================

INVESTIGATION_SYSTEM_PROMPT = """You are an expert DevOps investigation agent. Your job is to thoroughly investigate issues and provide actionable insights.

CRITICAL: STAY FOCUSED ON THE SPECIFIED ENVIRONMENT
- If the user asks about "staging", ONLY search staging logs
- If the user asks about "prod", ONLY search prod logs
- NEVER switch to a different environment unless explicitly asked
- Always include the environment in your search queries (e.g., "errors in cast-core staging")
- If a search returns no results for the specified environment, say "no errors found in [env]" - don't search other environments

When investigating an issue:

1. **Gather Evidence**
   - Search logs for errors in the SPECIFIED service/environment ONLY
   - Check recent deployments that might have caused the issue
   - Look for CloudWatch alarms that might be related

2. **Analyze Patterns**
   - Look for error patterns (repeated errors, error spikes)
   - Correlate timing with deployments
   - Only compare environments if the user explicitly asks

3. **Provide Clear Output**
   Format your findings as:

   ## 🔍 Investigation Summary
   [One sentence summary of what you found IN THE SPECIFIED ENVIRONMENT]

   ## 📋 Evidence Found
   - Key errors discovered (environment: [env])
   - Relevant deployment info
   - Alarm status

   ## 💡 Root Cause Hypothesis
   [Your best guess at what's causing the issue]

   ## 🔧 Recommended Actions
   1. [First action]
   2. [Second action]
   3. [Third action]

Be thorough but concise. Focus on actionable insights, not just data dumps.
If you can't find evidence IN THE SPECIFIED ENVIRONMENT, say so clearly - don't search other environments.
"""


def create_investigation_agent() -> Agent:
    """Create a Strands agent for deep issue investigation."""

    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-east-1")

    return Agent(
        model=model,
        tools=[
            search_logs,
            check_recent_deploys,
            get_error_summary,
            check_alarms,
            check_ecs_health,
        ],
        system_prompt=INVESTIGATION_SYSTEM_PROMPT,
    )


def investigate_issue(service: str, environment: str = None, description: str = None, max_steps: int = 10) -> dict:
    """Run a full multi-step investigation on an issue.

    This is the main entry point called by Claude Tool Use.
    The agent will autonomously call multiple tools to investigate.

    Args:
        service: Service name to investigate (e.g., 'emvio-dashboard-app')
        environment: Environment (prod, staging, dev) - optional
        description: User's description of the issue - optional
        max_steps: Maximum tool calls to make (default: 10)

    Returns:
        dict with 'report' containing the investigation findings
    """
    print(f"[Investigation] Starting investigation for {service} in {environment or 'all envs'}")

    try:
        agent = create_investigation_agent()

        # Build the investigation prompt
        prompt_parts = [f"Investigate issues with the service: **{service}**"]

        if environment:
            prompt_parts.append(
                f"Environment: **{environment}** (ONLY search this environment - do NOT check other environments)"
            )
        else:
            prompt_parts.append("Environment: Not specified - ask the user which environment to check")

        if description:
            prompt_parts.append(f'User reported: "{description}"')

        env_context = f" in {environment}" if environment else ""
        prompt_parts.append(
            f"""
Please:
1. Search for recent errors in {service}{env_context} (include environment in your search query)
2. Check recent deployments for {service}
3. Look for any active alarms
4. Analyze what you find and provide recommendations

IMPORTANT: Only report findings for the specified environment. If no environment was specified, ask the user which environment to check.
"""
        )

        prompt = "\n".join(prompt_parts)

        # Run the agent (it will autonomously call tools as needed)
        print(f"[Investigation] Running agent with prompt: {prompt[:100]}...")
        result = agent(prompt)

        # Extract the final message
        report = result.message if hasattr(result, "message") else str(result)

        print(f"[Investigation] Complete. Report length: {len(report)} chars")

        return {"report": report, "service": service, "environment": environment, "status": "completed"}

    except Exception as e:
        print(f"[Investigation] Error: {e}")
        import traceback

        traceback.print_exc()

        return {
            "report": f"Investigation encountered an error: {str(e)}. Try asking about specific aspects (logs, deploys, alarms) individually.",
            "service": service,
            "environment": environment,
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# LOCAL TESTING
# ============================================================================

if __name__ == "__main__":
    # Test the investigation agent locally
    print("=" * 60)
    print("INVESTIGATION AGENT TEST")
    print("=" * 60)

    result = investigate_issue(
        service="emvio-dashboard-app", environment="staging", description="App is loading slowly"
    )

    print("\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)
    print(result.get("report", "No report generated"))
