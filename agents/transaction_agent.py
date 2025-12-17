"""
Transaction Insights Agent for Merchants
Uses Strands SDK with Claude Sonnet on Amazon Bedrock
"""

import json
import pandas as pd
import os

from strands import Agent, tool

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "merchant-insights")


def load_merchant_data():
    """Load merchant transaction data from local JSON files."""
    datasets = {}
    data_files = {
        "transactions": "transactions.json",
        "settlements": "settlements.json",
        "merchants": "merchants.json",
    }

    for name, filename in data_files.items():
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                datasets[name] = json.load(f)

    return datasets


# Load data at module level
DATASETS = load_merchant_data()


@tool
def get_transaction_summary(time_period: str = "week", merchant_id: str = "merch_100") -> str:
    """Get a summary of transactions for a time period.

    Args:
        time_period: 'day', 'week', 'month', or 'all'
        merchant_id: The merchant ID to query

    Returns:
        str: JSON summary of transaction metrics
    """
    print(f"[Tool] get_transaction_summary: period={time_period}, merchant={merchant_id}")

    try:
        transactions = DATASETS.get("transactions", [])
        df = pd.DataFrame(transactions)

        if df.empty:
            return json.dumps({"error": "No transaction data available"})

        # Filter by merchant
        df = df[df['merchant_id'] == merchant_id]

        # Calculate metrics
        sales = df[df['transaction_type'] == 'sale']
        settled = sales[sales['status'] == 'settled']
        declined = sales[sales['status'] == 'declined']
        refunds = df[df['transaction_type'] == 'refund']
        chargebacks = df[df['status'] == 'chargeback']

        summary = {
            "period": time_period,
            "total_transactions": len(df),
            "total_sales": len(sales),
            "gross_volume": float(sales['amount'].sum()),
            "settled_volume": float(settled['amount'].sum()),
            "settled_count": len(settled),
            "declined_count": len(declined),
            "decline_rate": f"{(len(declined) / len(sales) * 100):.1f}%" if len(sales) > 0 else "0%",
            "refund_count": len(refunds),
            "refund_volume": float(refunds['amount'].sum()),
            "chargeback_count": len(chargebacks),
            "total_fees": float(df['fee'].sum()),
            "net_volume": float(df['net_amount'].sum()),
            "average_transaction": float(settled['amount'].mean()) if len(settled) > 0 else 0,
            "largest_transaction": float(settled['amount'].max()) if len(settled) > 0 else 0
        }

        print(f"[Tool] Summary: {summary['total_transactions']} transactions, ${summary['gross_volume']:.2f} volume")
        return json.dumps(summary, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to get summary: {str(e)}"})


@tool
def get_transactions_by_status(status: str, merchant_id: str = "merch_100") -> str:
    """Get transactions filtered by status.

    Args:
        status: 'settled', 'pending', 'declined', 'refunded', 'chargeback'
        merchant_id: The merchant ID to query

    Returns:
        str: JSON list of matching transactions
    """
    print(f"[Tool] get_transactions_by_status: status={status}, merchant={merchant_id}")

    try:
        transactions = DATASETS.get("transactions", [])
        df = pd.DataFrame(transactions)

        if df.empty:
            return json.dumps({"error": "No transaction data available"})

        # Filter
        df = df[df['merchant_id'] == merchant_id]
        df = df[df['status'] == status]

        results = df.to_dict('records')
        print(f"[Tool] Found {len(results)} {status} transactions")
        return json.dumps(results, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": f"Query failed: {str(e)}"})


@tool
def get_settlement_details(merchant_id: str = "merch_100") -> str:
    """Get settlement/payout details for a merchant.

    Args:
        merchant_id: The merchant ID to query

    Returns:
        str: JSON list of settlements with details
    """
    print(f"[Tool] get_settlement_details: merchant={merchant_id}")

    try:
        settlements = DATASETS.get("settlements", [])
        df = pd.DataFrame(settlements)

        if df.empty:
            return json.dumps({"error": "No settlement data available"})

        df = df[df['merchant_id'] == merchant_id]

        # Add summary stats
        total_deposited = df[df['status'] == 'deposited']['net_amount'].sum()
        pending = df[df['status'] == 'pending']['net_amount'].sum()

        result = {
            "settlements": df.to_dict('records'),
            "summary": {
                "total_deposited": float(total_deposited),
                "pending_amount": float(pending),
                "total_settlements": len(df),
                "total_fees_paid": float(df['total_fees'].sum()),
                "total_chargebacks": float(df['chargebacks'].sum()),
                "total_refunds": float(df['refunds'].sum())
            }
        }

        print(f"[Tool] Found {len(df)} settlements, ${total_deposited:.2f} deposited")
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": f"Query failed: {str(e)}"})


@tool
def analyze_card_types(merchant_id: str = "merch_100") -> str:
    """Analyze transaction breakdown by card type.

    Args:
        merchant_id: The merchant ID to query

    Returns:
        str: JSON breakdown of transactions by card type
    """
    print(f"[Tool] analyze_card_types: merchant={merchant_id}")

    try:
        transactions = DATASETS.get("transactions", [])
        df = pd.DataFrame(transactions)

        if df.empty:
            return json.dumps({"error": "No transaction data available"})

        df = df[df['merchant_id'] == merchant_id]
        sales = df[df['transaction_type'] == 'sale']

        breakdown = {}
        for card_type in sales['card_type'].unique():
            card_txns = sales[sales['card_type'] == card_type]
            settled = card_txns[card_txns['status'] == 'settled']
            breakdown[card_type] = {
                "transaction_count": len(card_txns),
                "volume": float(card_txns['amount'].sum()),
                "settled_volume": float(settled['amount'].sum()),
                "fees": float(settled['fee'].sum()),
                "avg_transaction": float(card_txns['amount'].mean()),
                "percentage_of_volume": f"{(card_txns['amount'].sum() / sales['amount'].sum() * 100):.1f}%"
            }

        print(f"[Tool] Analyzed {len(breakdown)} card types")
        return json.dumps(breakdown, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Analysis failed: {str(e)}"})


@tool
def get_decline_analysis(merchant_id: str = "merch_100") -> str:
    """Analyze declined transactions and reasons.

    Args:
        merchant_id: The merchant ID to query

    Returns:
        str: JSON analysis of declines with reasons
    """
    print(f"[Tool] get_decline_analysis: merchant={merchant_id}")

    try:
        transactions = DATASETS.get("transactions", [])
        df = pd.DataFrame(transactions)

        if df.empty:
            return json.dumps({"error": "No transaction data available"})

        df = df[df['merchant_id'] == merchant_id]
        declines = df[df['status'] == 'declined']

        if declines.empty:
            return json.dumps({"message": "No declined transactions found", "decline_count": 0})

        # Group by reason
        reasons = {}
        if 'decline_reason' in declines.columns:
            for reason in declines['decline_reason'].unique():
                reason_txns = declines[declines['decline_reason'] == reason]
                reasons[reason] = {
                    "count": len(reason_txns),
                    "total_amount": float(reason_txns['amount'].sum())
                }

        total_attempted = len(df[df['transaction_type'] == 'sale'])
        result = {
            "total_declines": len(declines),
            "decline_rate": f"{(len(declines) / total_attempted * 100):.1f}%" if total_attempted > 0 else "0%",
            "declined_volume": float(declines['amount'].sum()),
            "reasons": reasons,
            "declined_transactions": declines.to_dict('records')
        }

        print(f"[Tool] Found {len(declines)} declines")
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": f"Analysis failed: {str(e)}"})


@tool
def compare_periods(period1: str, period2: str, merchant_id: str = "merch_100") -> str:
    """Compare metrics between two time periods (placeholder - uses mock comparison).

    Args:
        period1: First period description (e.g., 'this week', 'December')
        period2: Second period description (e.g., 'last week', 'November')
        merchant_id: The merchant ID to query

    Returns:
        str: JSON comparison of key metrics
    """
    print(f"[Tool] compare_periods: {period1} vs {period2}")

    # For demo, return a simulated comparison
    comparison = {
        "period1": period1,
        "period2": period2,
        "metrics": {
            "volume": {"period1": 3500.00, "period2": 3200.00, "change": "+9.4%"},
            "transaction_count": {"period1": 20, "period2": 18, "change": "+11.1%"},
            "average_transaction": {"period1": 175.00, "period2": 177.78, "change": "-1.6%"},
            "decline_rate": {"period1": "10.0%", "period2": "12.0%", "change": "-2.0pp"},
            "fees": {"period1": 101.50, "period2": 92.80, "change": "+9.4%"}
        },
        "insights": [
            "Volume increased 9.4% compared to previous period",
            "Decline rate improved from 12% to 10%",
            "Average transaction size remained stable"
        ]
    }

    return json.dumps(comparison, indent=2)


def create_transaction_agent():
    """Create the transaction insights agent using Claude Sonnet on Bedrock."""

    system_prompt = """You are a helpful Transaction Insights Assistant for merchants.

Your role is to help merchants understand their payment data, answer questions about transactions, and provide actionable insights.

AVAILABLE DATA:
- transactions: Individual payment transactions (sales, refunds, chargebacks)
- settlements: Daily deposit/payout records
- merchants: Merchant account information

TOOLS AVAILABLE:
- get_transaction_summary: Get overview metrics (volume, counts, fees, etc.)
- get_transactions_by_status: Find transactions by status (settled, pending, declined, etc.)
- get_settlement_details: View payout/deposit information
- analyze_card_types: Break down transactions by Visa, Mastercard, Amex, etc.
- get_decline_analysis: Understand why transactions are being declined
- compare_periods: Compare metrics between time periods

RESPONSE STYLE:
- Be conversational and helpful, like a knowledgeable support agent
- Lead with the key insight or answer
- Use actual numbers from the data
- Explain fees and charges clearly
- Offer actionable suggestions when relevant
- Format currency with $ and 2 decimal places

COMMON QUESTIONS YOU HELP WITH:
- "Why did my sales drop this week?"
- "When will I get paid?"
- "What's my decline rate?"
- "Break down my fees"
- "What's my busiest card type?"
- "Show me my chargebacks"

Always use the tools to get real data before answering. Don't make up numbers."""

    return Agent(
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        tools=[
            get_transaction_summary,
            get_transactions_by_status,
            get_settlement_details,
            analyze_card_types,
            get_decline_analysis,
            compare_periods
        ],
        system_prompt=system_prompt
    )


# Create agent instance
agent = create_transaction_agent()


def run_agent(prompt: str) -> str:
    """Run the agent with a given prompt."""
    try:
        response = agent(prompt)
        return str(response)
    except Exception as e:
        return f"Error running agent: {str(e)}"


if __name__ == "__main__":
    print("Testing Transaction Insights Agent...")
    print("-" * 50)

    test_prompt = "Give me an overview of my transactions this week. How am I doing?"

    print(f"Prompt: {test_prompt}\n")
    response = run_agent(test_prompt)
    print(f"\nAgent Response:\n{response}")
