"""
DevOps Agent - Orchestrator (Agent of Agents)

Coordinates specialized agents for:
- Observability: Log analysis, code search, service health
- User Management: Onboarding/offboarding via Atlassian
"""

import json
import os
import sys

from strands import Agent, tool
from strands.models import BedrockModel

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================================
# AGENT REGISTRY - Lazy loaded agents
# ============================================================================

_agents = {}


def get_coralogix_agent():
    """Get or create the Coralogix agent."""
    if "coralogix" not in _agents:
        try:
            from coralogix_agent import create_coralogix_agent

            _agents["coralogix"] = create_coralogix_agent()
        except Exception as e:
            return None, f"Failed to load Coralogix agent: {e}"
    return _agents.get("coralogix"), None


def get_bitbucket_agent():
    """Get or create the Bitbucket/Code Search agent."""
    if "bitbucket" not in _agents:
        try:
            from bitbucket_agent import create_bitbucket_agent

            _agents["bitbucket"] = create_bitbucket_agent()
        except Exception as e:
            return None, f"Failed to load Bitbucket agent: {e}"
    return _agents.get("bitbucket"), None


# ============================================================================
# READ-ONLY TOOLS
# ============================================================================


@tool
def query_coralogix(question: str) -> str:
    """Query the Coralogix Log Analysis agent. READ-ONLY.

    Use this for:
    - Finding errors in services
    - Checking service health
    - Searching logs
    - Discovering available services

    Args:
        question: Natural language question about logs (e.g., "What errors are in cast-core prod?")
    """
    agent, error = get_coralogix_agent()
    if error:
        return error
    if not agent:
        return "Coralogix agent not available"

    try:
        result = agent(question)
        # Extract the text response
        if hasattr(result, "message"):
            return str(result.message)
        return str(result)
    except Exception as e:
        return f"Error querying Coralogix: {e}"


@tool
def search_code(question: str) -> str:
    """Search code across all repositories using semantic search. READ-ONLY.

    Use this for:
    - Finding configuration files (CSP, CORS, env vars)
    - Understanding how features are implemented
    - Finding code patterns across repos
    - Locating specific files

    Args:
        question: Natural language question about code (e.g., "Where is CSP configured?")

    Examples:
        - "Content Security Policy configuration"
        - "S3 file upload implementation"
        - "How is authentication implemented?"
        - "Where are CORS headers set?"
    """
    agent, error = get_bitbucket_agent()
    if error:
        return error
    if not agent:
        return "Code search agent not available. Make sure CODE_KB_ID is configured."

    try:
        result = agent(question)
        if hasattr(result, "message"):
            return str(result.message)
        return str(result)
    except Exception as e:
        return f"Error searching code: {e}"


@tool
def list_available_agents() -> str:
    """List all available specialized agents and their capabilities. READ-ONLY."""
    agents_info = """
AVAILABLE AGENTS:

1. CORALOGIX AGENT (ACTIVE)
   Status: Ready
   Capabilities:
   - discover_services: Find available log groups/services
   - get_recent_errors: Get errors by service/environment
   - get_service_logs: Get logs for specific services
   - get_log_count: Volume analysis
   - search_logs: Custom DataPrime queries
   - get_service_health: Error rate analysis

   Example queries:
   - "What errors are in cast-core prod?"
   - "Show me the health of all prod services"
   - "Search for timeout errors in the last 4 hours"

2. BITBUCKET/CODE SEARCH AGENT (ACTIVE)
   Status: Ready (requires CODE_KB_ID env var)
   Capabilities:
   - search_code: Semantic code search across all repos
   - search_code_in_repo: Search within specific repo
   - ask_about_code: AI-powered code Q&A
   - find_file: Find files by name
   - list_pull_requests: List PRs from Bitbucket
   - get_pipeline_status: CI/CD status

   Example queries:
   - "Where is Content Security Policy configured?"
   - "How is file upload implemented in dashboard?"
   - "Find serverless.yml files"

3. CLOUDWATCH AGENT (PLACEHOLDER)
   Status: Not implemented
   Would provide: AWS CloudWatch logs and metrics

4. CONFLUENCE AGENT (PLACEHOLDER)
   Status: Not implemented
   Would provide: Documentation search

5. DATABASE AGENT (PLACEHOLDER)
   Status: Not implemented
   Would provide: Database queries (read-only)

6. RISK AGENT (PLACEHOLDER)
   Status: Not implemented
   Would provide: Risk scores, underwriting status
"""
    return agents_info


@tool
def get_system_overview() -> str:
    """Get a high-level overview of system status. READ-ONLY.

    Queries multiple agents to provide a summary of:
    - Service health from Coralogix
    - Any active errors or alerts
    """
    results = []

    # Query Coralogix for health
    agent, error = get_coralogix_agent()
    if agent:
        try:
            health_result = agent("Give me a quick health summary of prod services - just error counts")
            if hasattr(health_result, "message"):
                results.append(f"LOG HEALTH:\n{health_result.message}")
            else:
                results.append(f"LOG HEALTH:\n{health_result}")
        except Exception as e:
            results.append(f"LOG HEALTH: Error - {e}")
    else:
        results.append(f"LOG HEALTH: {error or 'Not available'}")

    return "\n\n".join(results)


@tool
def investigate_service(service_name: str, environment: str = "prod") -> str:
    """Investigate a specific service across all available data sources. READ-ONLY.

    This tool queries BOTH logs AND code to provide comprehensive analysis.

    Args:
        service_name: Name of the service (e.g., 'emvio-dashboard-app', 'cast-core')
        environment: Environment to check - prod, dev, staging
    """
    results = []
    results.append(f"=== INVESTIGATING: {service_name} ({environment}) ===\n")

    # Query Coralogix for logs
    coralogix_agent, error = get_coralogix_agent()
    if coralogix_agent:
        try:
            # Get recent errors
            error_result = coralogix_agent(f"Get recent errors for {service_name} in {environment} environment")
            if hasattr(error_result, "message"):
                results.append(f"RECENT ERRORS:\n{error_result.message}")
            else:
                results.append(f"RECENT ERRORS:\n{error_result}")

            # Get health
            health_result = coralogix_agent(f"What's the health of {service_name} in {environment}?")
            if hasattr(health_result, "message"):
                results.append(f"\nHEALTH STATUS:\n{health_result.message}")
            else:
                results.append(f"\nHEALTH STATUS:\n{health_result}")

        except Exception as e:
            results.append(f"LOG ANALYSIS: Error - {e}")
    else:
        results.append(f"LOG ANALYSIS: {error or 'Coralogix not available'}")

    # Query Code for configuration
    bitbucket_agent, error = get_bitbucket_agent()
    if bitbucket_agent:
        try:
            code_result = bitbucket_agent(f"Search for configuration and key files in {service_name}")
            if hasattr(code_result, "message"):
                results.append(f"\nCODE ANALYSIS:\n{code_result.message}")
            else:
                results.append(f"\nCODE ANALYSIS:\n{code_result}")
        except Exception as e:
            results.append(f"\nCODE ANALYSIS: Error - {e}")
    else:
        results.append(f"\nCODE ANALYSIS: {error or 'Not available'}")

    return "\n".join(results)


@tool
def search_across_systems(query: str) -> str:
    """Search for a term/pattern across ALL available systems. READ-ONLY.

    Searches BOTH logs (Coralogix) AND code (Knowledge Base).

    Args:
        query: Search term (e.g., 'CSP', 'timeout', 'S3 upload', 'merchant-123')
    """
    results = []
    results.append(f"=== SEARCHING FOR: '{query}' ===\n")

    # Search Coralogix logs
    coralogix_agent, error = get_coralogix_agent()
    if coralogix_agent:
        try:
            log_result = coralogix_agent(f"Search logs for '{query}' in the last 4 hours")
            if hasattr(log_result, "message"):
                results.append(f"CORALOGIX LOGS:\n{log_result.message}")
            else:
                results.append(f"CORALOGIX LOGS:\n{log_result}")
        except Exception as e:
            results.append(f"CORALOGIX LOGS: Error - {e}")
    else:
        results.append(f"CORALOGIX LOGS: {error or 'Not available'}")

    # Search Code
    bitbucket_agent, error = get_bitbucket_agent()
    if bitbucket_agent:
        try:
            code_result = bitbucket_agent(f"Search code for '{query}'")
            if hasattr(code_result, "message"):
                results.append(f"\nCODE SEARCH:\n{code_result.message}")
            else:
                results.append(f"\nCODE SEARCH:\n{code_result}")
        except Exception as e:
            results.append(f"\nCODE SEARCH: Error - {e}")
    else:
        results.append(f"\nCODE SEARCH: {error or 'Not available'}")

    return "\n".join(results)


@tool
def compare_environments(service_name: str) -> str:
    """Compare a service across environments (prod vs dev vs staging). READ-ONLY.

    Args:
        service_name: Name of the service to compare
    """
    results = []
    results.append(f"=== ENVIRONMENT COMPARISON: {service_name} ===\n")

    agent, error = get_coralogix_agent()
    if agent:
        for env in ["prod", "dev", "staging"]:
            try:
                result = agent(f"Get error count and health for {service_name} in {env} environment in the last hour")
                if hasattr(result, "message"):
                    results.append(f"{env.upper()}:\n{result.message}\n")
                else:
                    results.append(f"{env.upper()}:\n{result}\n")
            except Exception as e:
                results.append(f"{env.upper()}: Error - {e}\n")
    else:
        results.append(f"Cannot compare - {error or 'Coralogix not available'}")

    return "\n".join(results)


# ============================================================================
# MCP TOOL HELPERS
# ============================================================================

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "https://mcp.mrrobot.dev")


def _call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool via the HTTP API."""
    import json

    import requests

    try:
        response = requests.post(
            f"{MCP_SERVER_URL}/sse",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        # Extract the text content from MCP response
        if "result" in result and "content" in result["result"]:
            content = result["result"]["content"]
            if content and len(content) > 0:
                text = content[0].get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"response": text}
        return result
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# ONBOARDING/OFFBOARDING TOOLS
# ============================================================================


@tool
def list_atlassian_users(limit: int = 50) -> str:
    """List users in the Atlassian organization.

    Args:
        limit: Maximum number of users to return (default: 50)

    Returns:
        str: JSON with list of Atlassian users
    """
    result = _call_mcp_tool("atlassian_list_users", {"limit": limit})
    return json.dumps(result, indent=2)


@tool
def list_atlassian_groups() -> str:
    """List all groups in the Atlassian organization.

    Returns:
        str: JSON with list of groups and their member counts
    """
    result = _call_mcp_tool("atlassian_list_groups", {"limit": 100})
    return json.dumps(result, indent=2)


@tool
def onboard_employee(
    account_id: str,
    groups: list,
    verify: bool = True,
) -> str:
    """Onboard a new employee to Atlassian by adding them to groups.

    This is the orchestration tool for onboarding. It adds the user to
    all specified groups (e.g., jira-users, confluence-users, team groups).

    Args:
        account_id: The Atlassian account ID of the user
        groups: List of group IDs to add the user to
        verify: Whether to verify the user was added (default: True)

    Returns:
        str: Summary of onboarding actions taken
    """
    results = []
    results.append(f"=== ONBOARDING USER: {account_id} ===\n")

    successful = []
    failed = []

    for group_id in groups:
        result = _call_mcp_tool(
            "atlassian_add_user_to_group",
            {
                "group_id": group_id,
                "account_id": account_id,
            },
        )

        if "error" in result:
            failed.append({"group": group_id, "error": result["error"]})
            results.append(f"FAILED: Add to group {group_id} - {result['error']}")
        else:
            successful.append(group_id)
            results.append(f"SUCCESS: Added to group {group_id}")

    results.append(f"\n=== SUMMARY ===")
    results.append(f"Successful: {len(successful)} groups")
    results.append(f"Failed: {len(failed)} groups")

    if failed:
        results.append(f"\nFailed groups: {json.dumps(failed, indent=2)}")

    return "\n".join(results)


@tool
def offboard_employee(
    account_id: str,
    suspend: bool = True,
    remove_from_groups: bool = True,
) -> str:
    """Offboard an employee from Atlassian.

    This orchestrates the offboarding process:
    1. Suspends the user's access
    2. Optionally removes them from all groups

    Args:
        account_id: The Atlassian account ID of the user
        suspend: Whether to suspend the account (default: True)
        remove_from_groups: Whether to remove from all groups (default: True)

    Returns:
        str: Summary of offboarding actions taken
    """
    results = []
    results.append(f"=== OFFBOARDING USER: {account_id} ===\n")

    # Step 1: Suspend the user
    if suspend:
        result = _call_mcp_tool("atlassian_suspend_user", {"account_id": account_id})
        if "error" in result:
            results.append(f"FAILED: Suspend user - {result['error']}")
        else:
            results.append(f"SUCCESS: User suspended")

    # Step 2: Get groups and remove from all
    if remove_from_groups:
        groups_result = _call_mcp_tool("atlassian_list_groups", {"limit": 100})
        if "formatted_groups" in groups_result:
            results.append(f"\nRemoving from groups...")
            for group in groups_result["formatted_groups"]:
                group_id = group["group_id"]
                remove_result = _call_mcp_tool(
                    "atlassian_remove_user_from_group",
                    {
                        "group_id": group_id,
                        "account_id": account_id,
                    },
                )
                if "error" not in remove_result:
                    results.append(f"  Removed from: {group['name']}")

    results.append(f"\n=== OFFBOARDING COMPLETE ===")
    return "\n".join(results)


@tool
def search_atlassian_user(email_or_name: str) -> str:
    """Search for a user in Atlassian by email or name.

    Args:
        email_or_name: Email address or name to search for

    Returns:
        str: Matching users found
    """
    # Get all users and filter locally (Atlassian API doesn't have search)
    result = _call_mcp_tool("atlassian_list_users", {"limit": 200})

    if "formatted_users" not in result:
        return json.dumps(result, indent=2)

    search_term = email_or_name.lower()
    matches = []

    for user in result["formatted_users"]:
        name = (user.get("name") or "").lower()
        email = (user.get("email") or "").lower()

        if search_term in name or search_term in email:
            matches.append(user)

    return json.dumps(
        {
            "search_term": email_or_name,
            "matches_found": len(matches),
            "users": matches,
        },
        indent=2,
    )


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================

DEVOPS_TOOLS = [
    # Observability tools
    query_coralogix,
    search_code,
    list_available_agents,
    get_system_overview,
    investigate_service,
    search_across_systems,
    compare_environments,
    # Onboarding/Offboarding tools
    list_atlassian_users,
    list_atlassian_groups,
    search_atlassian_user,
    onboard_employee,
    offboard_employee,
]

SYSTEM_PROMPT = """You are a DevOps Assistant that orchestrates specialized tools and agents.

You have TWO modes of operation:

MODE 1: OBSERVABILITY (READ-ONLY)
- Query Coralogix logs for errors, health, and patterns
- Search code across all repositories
- Investigate services across data sources
- Compare environments (prod/dev/staging)

MODE 2: USER MANAGEMENT (ONBOARDING/OFFBOARDING)
- List and search Atlassian users
- Onboard new employees (add to groups)
- Offboard employees (suspend + remove from groups)

AVAILABLE TOOLS:

**Observability:**
- query_coralogix: Ask log-related questions
- search_code: Semantic code search
- get_system_overview: Quick health summary
- investigate_service: Deep dive into a service
- search_across_systems: Search logs AND code
- compare_environments: Compare prod/dev/staging

**User Management:**
- list_atlassian_users: List all Atlassian users
- list_atlassian_groups: List all groups
- search_atlassian_user: Find user by email/name
- onboard_employee: Add user to groups (orchestrated)
- offboard_employee: Suspend + remove from groups (orchestrated)

HOW TO USE:
- "What errors in prod?" -> query_coralogix
- "Find CSP config" -> search_code
- "Show Atlassian users" -> list_atlassian_users
- "Find user john@company.com" -> search_atlassian_user
- "Onboard John to engineering" -> First search_atlassian_user, then list_atlassian_groups, then onboard_employee
- "Offboard Jane" -> First search_atlassian_user to get ID, then offboard_employee

ONBOARDING WORKFLOW:
1. search_atlassian_user to find the user's account_id
2. list_atlassian_groups to see available groups
3. onboard_employee with account_id and list of group_ids

OFFBOARDING WORKFLOW:
1. search_atlassian_user to find the user's account_id
2. offboard_employee with account_id (suspends + removes from all groups)

RESPONSE STYLE:
- Be concise and actionable
- For onboarding/offboarding, confirm actions taken
- Always verify user identity before actions
- Report any failures clearly
"""


def create_devops_agent():
    """Create and return a DevOps orchestrator agent."""
    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-west-2")
    return Agent(model=model, tools=DEVOPS_TOOLS, system_prompt=SYSTEM_PROMPT)


# For direct import
devops_agent = None  # Lazy - use create_devops_agent()
