"""
Risk Agent - Underwriting and risk assessment
Connects to: mrrobot-risk-rest, emvio-underwriting-service
"""
import os

from strands import Agent, tool
from strands.models import BedrockModel

# Configuration
RISK_SERVICE_URL = os.environ.get('MRROBOT_RISK_URL', 'https://risk.mrrobotpay.com')
UNDERWRITING_SERVICE_URL = os.environ.get('UNDERWRITING_URL', 'https://underwriting.mrrobotpay.com')
API_KEY = os.environ.get('MRROBOT_INTERNAL_API_KEY', '')

# ============================================================================
# MRROBOT-RISK-REST TOOLS
# ============================================================================

@tool
def get_risk_assessment(merchant_id: str) -> str:
    """Get risk assessment from mrrobot-risk-rest for a merchant.

    Args:
        merchant_id: Merchant ID or MID
    """
    # TODO: Call mrrobot-risk-rest API
    # GET {RISK_SERVICE_URL}/api/v1/merchants/{merchant_id}/risk
    return "TODO: Implement mrrobot-risk-rest call"


@tool
def get_risk_score(merchant_id: str) -> str:
    """Get current risk score from mrrobot-risk-rest.

    Args:
        merchant_id: Merchant ID or MID
    """
    # TODO: Call mrrobot-risk-rest API
    # GET {RISK_SERVICE_URL}/api/v1/merchants/{merchant_id}/score
    return "TODO: Implement mrrobot-risk-rest call"


@tool
def get_risk_factors(merchant_id: str) -> str:
    """Get risk factors contributing to merchant's score.

    Args:
        merchant_id: Merchant ID or MID
    """
    # TODO: Call mrrobot-risk-rest API
    # GET {RISK_SERVICE_URL}/api/v1/merchants/{merchant_id}/factors
    return "TODO: Implement mrrobot-risk-rest call"


@tool
def get_chargeback_metrics(merchant_id: str, months: int = 6) -> str:
    """Get chargeback metrics from mrrobot-risk-rest.

    Args:
        merchant_id: Merchant ID
        months: Number of months of history
    """
    # TODO: Call mrrobot-risk-rest API
    # GET {RISK_SERVICE_URL}/api/v1/merchants/{merchant_id}/chargebacks?months={months}
    return "TODO: Implement mrrobot-risk-rest call"


@tool
def get_fraud_alerts(merchant_id: str = "", status: str = "active") -> str:
    """Get fraud alerts from mrrobot-risk-rest.

    Args:
        merchant_id: Filter by merchant (optional)
        status: Alert status - active, resolved, all
    """
    # TODO: Call mrrobot-risk-rest API
    # GET {RISK_SERVICE_URL}/api/v1/alerts?merchant_id={merchant_id}&status={status}
    return "TODO: Implement mrrobot-risk-rest call"


# ============================================================================
# EMVIO-UNDERWRITING-SERVICE TOOLS
# ============================================================================

@tool
def get_underwriting_status(application_id: str) -> str:
    """Get underwriting status from emvio-underwriting-service.

    Args:
        application_id: Merchant application ID
    """
    # TODO: Call emvio-underwriting-service API
    # GET {UNDERWRITING_SERVICE_URL}/api/v1/applications/{application_id}/status
    return "TODO: Implement emvio-underwriting-service call"


@tool
def get_underwriting_decision(application_id: str) -> str:
    """Get underwriting decision details from emvio-underwriting-service.

    Args:
        application_id: Merchant application ID
    """
    # TODO: Call emvio-underwriting-service API
    # GET {UNDERWRITING_SERVICE_URL}/api/v1/applications/{application_id}/decision
    return "TODO: Implement emvio-underwriting-service call"


@tool
def get_underwriting_checklist(application_id: str) -> str:
    """Get underwriting checklist status from emvio-underwriting-service.

    Args:
        application_id: Merchant application ID
    """
    # TODO: Call emvio-underwriting-service API
    # GET {UNDERWRITING_SERVICE_URL}/api/v1/applications/{application_id}/checklist
    return "TODO: Implement emvio-underwriting-service call"


@tool
def get_mcc_guidelines(mcc_code: str) -> str:
    """Get underwriting guidelines for an MCC from emvio-underwriting-service.

    Args:
        mcc_code: Merchant Category Code
    """
    # TODO: Call emvio-underwriting-service API
    # GET {UNDERWRITING_SERVICE_URL}/api/v1/guidelines/mcc/{mcc_code}
    return "TODO: Implement emvio-underwriting-service call"


@tool
def search_applications(status: str = "pending", days_back: int = 30, limit: int = 50) -> str:
    """Search underwriting applications from emvio-underwriting-service.

    Args:
        status: Application status - pending, approved, declined, review
        days_back: How far back to search
        limit: Max results
    """
    # TODO: Call emvio-underwriting-service API
    # GET {UNDERWRITING_SERVICE_URL}/api/v1/applications?status={status}&days={days_back}&limit={limit}
    return "TODO: Implement emvio-underwriting-service call"


@tool
def get_reserve_calculation(merchant_id: str) -> str:
    """Get reserve calculation from emvio-underwriting-service.

    Args:
        merchant_id: Merchant ID
    """
    # TODO: Call emvio-underwriting-service API
    # GET {UNDERWRITING_SERVICE_URL}/api/v1/merchants/{merchant_id}/reserves
    return "TODO: Implement emvio-underwriting-service call"


# Export tools list
RISK_TOOLS = [
    # mrrobot-risk-rest
    get_risk_assessment,
    get_risk_score,
    get_risk_factors,
    get_chargeback_metrics,
    get_fraud_alerts,
    # emvio-underwriting-service
    get_underwriting_status,
    get_underwriting_decision,
    get_underwriting_checklist,
    get_mcc_guidelines,
    search_applications,
    get_reserve_calculation,
]

# System prompt
SYSTEM_PROMPT = """You are an Underwriting and Risk Assessment Assistant for MrRobot.

You connect to two backend services:

1. MRROBOT-RISK-REST - Risk monitoring and fraud detection
   - Risk scores and assessments
   - Chargeback metrics
   - Fraud alerts
   - Risk factors analysis

2. EMVIO-UNDERWRITING-SERVICE - Merchant underwriting
   - Application status and decisions
   - Underwriting checklists
   - MCC guidelines
   - Reserve calculations

AVAILABLE TOOLS:

From mrrobot-risk-rest:
- get_risk_assessment - Full risk assessment for merchant
- get_risk_score - Current risk score
- get_risk_factors - Factors contributing to score
- get_chargeback_metrics - Chargeback history and rates
- get_fraud_alerts - Active fraud alerts

From emvio-underwriting-service:
- get_underwriting_status - Application status
- get_underwriting_decision - Decision details
- get_underwriting_checklist - Checklist completion
- get_mcc_guidelines - Guidelines by MCC
- search_applications - Find applications
- get_reserve_calculation - Reserve requirements

RISK SCORE INTERPRETATION:
- 0-30: Low Risk (green)
- 31-60: Medium Risk (yellow)
- 61-80: High Risk (orange)
- 81-100: Critical Risk (red)

Always explain risk factors clearly and recommend next steps.
"""

# Create agent
def create_risk_agent():
    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        region_name="us-west-2"
    )
    return Agent(
        model=model,
        tools=RISK_TOOLS,
        system_prompt=SYSTEM_PROMPT
    )

risk_agent = None  # Lazy initialization
