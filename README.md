# Merchant Insights Platform

AI-powered transaction insights for merchants using **Strands SDK** + **Claude Sonnet on Amazon Bedrock**.

## Current: Transaction Insights Agent

Help merchants understand their payment data through natural language:

```
"Give me an overview of my transactions"
"Why are cards being declined?"
"Break down my fees by card type"
"When will I get my next deposit?"
```

### Architecture

```
Merchant → Streamlit UI → Strands Agent → Claude Sonnet (Bedrock)
                              ↓
                         Tool Calls
                    (query transactions,
                     analyze declines,
                     get settlements)
```

### Quick Start

```bash
# Set up
cd ~/Mine/strands-agent-app
source venv/bin/activate

# Run (requires AWS credentials)
AWS_PROFILE=dev streamlit run app.py
```

Open http://localhost:8501

---

## Roadmap: Additional Agents

### Phase 2: Settlement/Payout Agent

**Purpose:** Help merchants understand when and how they get paid

**Sample Questions:**
- "When will I get paid for yesterday's sales?"
- "Why is this deposit less than I expected?"
- "Show me my payout schedule"
- "Reconcile my bank statement with my settlements"

**Tools Needed:**
- `get_pending_settlements` - Show upcoming payouts
- `explain_settlement` - Break down a specific deposit
- `reconcile_deposits` - Match settlements to bank records
- `get_hold_reasons` - Explain any fund holds

**Data Required:**
- Settlement schedules
- Bank deposit records
- Hold/reserve information
- Fee breakdown per settlement

---

### Phase 3: Chargeback Assistant

**Purpose:** Help merchants manage and respond to disputes

**Sample Questions:**
- "I got a chargeback - what do I do?"
- "What evidence do I need to fight this dispute?"
- "Show me my chargeback rate"
- "Why did I get charged $15 for this dispute?"

**Tools Needed:**
- `get_chargeback_details` - Full dispute information
- `suggest_evidence` - Recommend what to submit
- `draft_response` - Help write dispute response
- `analyze_chargeback_trends` - Identify patterns

**Data Required:**
- Dispute records with reason codes
- Original transaction details
- Evidence templates by reason code
- Chargeback fee schedule

---

### Phase 4: Integration Helper

**Purpose:** Help merchants integrate the payment API

**Sample Questions:**
- "How do I process a refund via API?"
- "Show me a code example for recurring billing"
- "My API call is returning error 422 - what's wrong?"
- "What webhooks should I set up?"

**Tools Needed:**
- `search_docs` - Search API documentation
- `get_code_example` - Return code snippets
- `explain_error` - Decode error messages
- `validate_request` - Check API request format

**Data Required:**
- API documentation (indexed)
- Code examples by language
- Error code reference
- Webhook event catalog

---

### Phase 5: Fee Analyzer

**Purpose:** Help merchants understand and optimize processing costs

**Sample Questions:**
- "Break down my fees for this month"
- "Why was this transaction charged 3.5% instead of 2.9%?"
- "How can I reduce my processing costs?"
- "What would I save with a different pricing plan?"

**Tools Needed:**
- `analyze_fees` - Detailed fee breakdown
- `explain_rate` - Why a specific rate was applied
- `suggest_optimizations` - Cost reduction tips
- `compare_pricing` - Model different rate structures

**Data Required:**
- Fee schedule by card type
- Interchange rates
- Qualification criteria
- Historical fee data

---

## Project Structure

```
strands-agent-app/
├── app.py                      # Streamlit frontend
├── agent.py                    # Transaction Insights Agent
├── requirements.txt
├── data/
│   ├── merchant-insights/      # Transaction data
│   │   ├── transactions.json
│   │   ├── settlements.json
│   │   └── merchants.json
│   └── player-analytics/       # Original demo data
│       └── ...
├── infra/                      # CDK (JavaScript)
│   └── ...
└── scripts/
    ├── deploy.sh
    └── copy-to-ec2.sh
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| AI Agent | Strands SDK |
| LLM | Claude Sonnet 4 (Bedrock) |
| Frontend | Streamlit |
| Hosting | EC2 + CloudFront |
| IaC | AWS CDK (JavaScript) |

## Development

### Adding a New Agent

1. Create agent file (e.g., `chargeback_agent.py`)
2. Define tools with `@tool` decorator
3. Create agent with system prompt
4. Add UI page in `app.py`
5. Add sample data to `data/` folder

### Tool Pattern

```python
from strands import Agent, tool

@tool
def my_tool(param: str) -> str:
    """Tool description for the LLM.

    Args:
        param: What this parameter does

    Returns:
        str: JSON result
    """
    # Query data, call APIs, etc.
    return json.dumps(result)

agent = Agent(
    model="anthropic.claude-sonnet-4-20250514-v1:0",
    tools=[my_tool],
    system_prompt="You are..."
)
```

## AWS Deployment

```bash
# Configure AWS
aws sso login --profile dev

# Deploy infrastructure
cd infra && npm install && npx cdk deploy

# Copy app to EC2
./scripts/copy-to-ec2.sh <EC2_IP>
```

## License

MIT License
