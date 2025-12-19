"""
MrRobot AI Agents

Specialized AI assistants with domain-specific tools.

ACTIVE AGENTS:
- devops_agent: Orchestrator for observability + onboarding/offboarding
- coralogix_agent: Log analysis with DataPrime queries
- bitbucket_agent: Code search and repository access
- cve_agent: CVE vulnerability scanning
- vulnerability_agent: Security vulnerability analysis
- transaction_agent: Transaction and merchant analytics

PLACEHOLDER AGENTS (not yet implemented):
- cloudwatch_agent, confluence_agent, database_agent, hr_agent, risk_agent
"""

# Active agents
from .devops_agent import DEVOPS_TOOLS, create_devops_agent
from .coralogix_agent import coralogix_agent, run_coralogix_agent, create_coralogix_agent
from .bitbucket_agent import BITBUCKET_TOOLS, bitbucket_agent
from .cve_agent import cve_agent, run_cve_agent
from .vulnerability_agent import vulnerability_agent, run_vulnerability_agent
from .transaction_agent import agent as transaction_agent
from .transaction_agent import run_agent as run_transaction_agent

# Placeholder agents (exported for backwards compatibility)
from .cloudwatch_agent import CLOUDWATCH_TOOLS, cloudwatch_agent
from .confluence_agent import CONFLUENCE_TOOLS, confluence_agent
from .database_agent import DATABASE_TOOLS, database_agent
from .hr_agent import HR_TOOLS, hr_agent
from .risk_agent import RISK_TOOLS, risk_agent

__all__ = [
    # Active orchestrator
    "create_devops_agent",
    "DEVOPS_TOOLS",
    # Active specialized agents
    "coralogix_agent",
    "create_coralogix_agent",
    "run_coralogix_agent",
    "bitbucket_agent",
    "BITBUCKET_TOOLS",
    "cve_agent",
    "run_cve_agent",
    "vulnerability_agent",
    "run_vulnerability_agent",
    "transaction_agent",
    "run_transaction_agent",
    # Placeholder agents
    "cloudwatch_agent",
    "CLOUDWATCH_TOOLS",
    "confluence_agent",
    "CONFLUENCE_TOOLS",
    "database_agent",
    "DATABASE_TOOLS",
    "hr_agent",
    "HR_TOOLS",
    "risk_agent",
    "RISK_TOOLS",
]
