"""
DevOps Agent - Orchestrator (Agent of Agents)
READ-ONLY: This agent only reads/queries data, never modifies anything.

Coordinates specialized agents to answer complex cross-system queries.
"""

import os
import sys

from strands import Agent, tool
from strands.models import BedrockModel

# Add parent directory to path to import agents
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
            from agents.bitbucket_agent import create_bitbucket_agent

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
# AGENT CONFIGURATION
# ============================================================================

DEVOPS_TOOLS = [
    query_coralogix,
    search_code,
    list_available_agents,
    get_system_overview,
    investigate_service,
    search_across_systems,
    compare_environments,
]

SYSTEM_PROMPT = """You are a DevOps Assistant that orchestrates specialized agents to answer questions.

IMPORTANT: You are READ-ONLY. You can query and analyze but NEVER modify, deploy, or change anything.

YOUR CAPABILITIES:
1. Query Coralogix logs for errors, health, and patterns
2. Search code across all repositories (semantic search)
3. Investigate specific services across data sources
4. Search across multiple systems (logs + code)
5. Compare environments (prod/dev/staging)
6. Get system-wide overviews

AVAILABLE TOOLS:
- query_coralogix: Ask the Coralogix agent any log-related question
- search_code: Search code semantically (CSP configs, implementations, patterns)
- list_available_agents: See all agents and their status
- get_system_overview: Quick health summary
- investigate_service: Deep dive into a service (logs + code)
- search_across_systems: Search for patterns in logs AND code
- compare_environments: Compare service across prod/dev/staging

HOW TO USE:
- For log questions -> use query_coralogix
- For code/config questions -> use search_code
- For service issues -> use investigate_service (combines logs + code)
- For broad searches -> use search_across_systems
- For comparisons -> use compare_environments

RESPONSE STYLE:
- Be concise and actionable
- Highlight critical issues first
- Include relevant code locations when found
- Suggest next steps when appropriate
- Admit when data is unavailable

Example interactions:
- "What's wrong with payment-service?" -> investigate_service("payment-service", "prod")
- "Any errors in prod?" -> query_coralogix("Show me all prod errors in the last hour")
- "Where is CSP configured in dashboard?" -> search_code("Content Security Policy emvio-dashboard-app")
- "Search for timeout issues" -> search_across_systems("timeout")
"""


def create_devops_agent():
    """Create and return a DevOps orchestrator agent."""
    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-west-2")
    return Agent(model=model, tools=DEVOPS_TOOLS, system_prompt=SYSTEM_PROMPT)


# For direct import
devops_agent = None  # Lazy - use create_devops_agent()
