# MrRobot AI Agents
# Each agent is a specialized AI assistant with domain-specific tools

from .bitbucket_agent import BITBUCKET_TOOLS, bitbucket_agent
from .cloudwatch_agent import CLOUDWATCH_TOOLS, cloudwatch_agent
from .confluence_agent import CONFLUENCE_TOOLS, confluence_agent
from .coralogix_agent import coralogix_agent, run_coralogix_agent
from .cve_agent import cve_agent, run_cve_agent
from .database_agent import DATABASE_TOOLS, database_agent
from .devops_agent import DEVOPS_TOOLS, devops_agent
from .hr_agent import HR_TOOLS, hr_agent
from .risk_agent import RISK_TOOLS, risk_agent
from .transaction_agent import agent as transaction_agent
from .transaction_agent import run_agent as run_transaction_agent
from .vulnerability_agent import run_vulnerability_agent, vulnerability_agent

__all__ = [
    # Core agents
    "bitbucket_agent",
    "BITBUCKET_TOOLS",
    "cloudwatch_agent",
    "CLOUDWATCH_TOOLS",
    "confluence_agent",
    "CONFLUENCE_TOOLS",
    "database_agent",
    "DATABASE_TOOLS",
    "devops_agent",
    "DEVOPS_TOOLS",
    "hr_agent",
    "HR_TOOLS",
    "risk_agent",
    "RISK_TOOLS",
    # Specialized agents
    "coralogix_agent",
    "run_coralogix_agent",
    "cve_agent",
    "run_cve_agent",
    "transaction_agent",
    "run_transaction_agent",
    "vulnerability_agent",
    "run_vulnerability_agent",
]
