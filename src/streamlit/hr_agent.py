"""
HR Agent - Human Resources assistant
Tools for HR policies, employee information, and HR-related queries.
"""

import os

from strands import Agent, tool
from strands.models import BedrockModel

# Configuration
HR_SYSTEM_URL = os.environ.get("HR_SYSTEM_URL", "")

# ============================================================================
# TOOLS
# ============================================================================


@tool
def search_policies(query: str, category: str = "all") -> str:
    """Search HR policies and handbooks.

    Args:
        query: What to search for
        category: Policy category - benefits, pto, conduct, safety, or 'all'
    """
    # TODO: Implement HR policy search
    return "TODO: Implement search_policies"


@tool
def get_policy_details(policy_name: str) -> str:
    """Get detailed information about a specific HR policy.

    Args:
        policy_name: Name of the policy
    """
    # TODO: Implement policy retrieval
    return "TODO: Implement get_policy_details"


@tool
def get_benefits_info(benefit_type: str = "all") -> str:
    """Get information about employee benefits.

    Args:
        benefit_type: Type of benefit - health, dental, vision, 401k, pto, or 'all'
    """
    # TODO: Implement benefits lookup
    return "TODO: Implement get_benefits_info"


@tool
def get_pto_policy() -> str:
    """Get PTO/vacation policy details including accrual rates."""
    # TODO: Implement PTO policy retrieval
    return "TODO: Implement get_pto_policy"


@tool
def get_holiday_schedule(year: int = 2025) -> str:
    """Get company holiday schedule.

    Args:
        year: Year for holiday schedule
    """
    # TODO: Implement holiday schedule retrieval
    return "TODO: Implement get_holiday_schedule"


@tool
def get_onboarding_checklist(role_type: str = "engineering") -> str:
    """Get new employee onboarding checklist.

    Args:
        role_type: Role type - engineering, sales, operations, etc.
    """
    # TODO: Implement onboarding checklist
    return "TODO: Implement get_onboarding_checklist"


@tool
def get_org_chart(department: str = "all") -> str:
    """Get organization chart information.

    Args:
        department: Department name or 'all'
    """
    # TODO: Implement org chart retrieval
    return "TODO: Implement get_org_chart"


@tool
def find_contact(name: str = "", department: str = "", role: str = "") -> str:
    """Find employee contact information.

    Args:
        name: Employee name (partial match)
        department: Filter by department
        role: Filter by role/title
    """
    # TODO: Implement contact lookup
    return "TODO: Implement find_contact"


# Export tools list
HR_TOOLS = [
    search_policies,
    get_policy_details,
    get_benefits_info,
    get_pto_policy,
    get_holiday_schedule,
    get_onboarding_checklist,
    get_org_chart,
    find_contact,
]

# System prompt
SYSTEM_PROMPT = """You are an HR Assistant for MrRobot employees.

You help employees with:
- Finding HR policies and procedures
- Understanding benefits
- PTO and holiday information
- Onboarding guidance
- Finding colleagues and org structure

AVAILABLE TOOLS:
1. search_policies - Search HR policies
2. get_policy_details - Get specific policy details
3. get_benefits_info - Benefits information
4. get_pto_policy - PTO accrual and rules
5. get_holiday_schedule - Company holidays
6. get_onboarding_checklist - New hire checklist
7. get_org_chart - Organization structure
8. find_contact - Find employee contacts

IMPORTANT:
- Always provide accurate policy information
- Direct employees to HR for sensitive matters
- Do not disclose confidential employee data
- Encourage employees to check with HR for specific situations
"""


# Create agent
def create_hr_agent():
    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-west-2")
    return Agent(model=model, tools=HR_TOOLS, system_prompt=SYSTEM_PROMPT)


hr_agent = None  # Lazy initialization
