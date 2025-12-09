# Merchant Insights AI Agent - Demo

## Overview

A proof-of-concept AI-powered assistant that helps merchants understand their payment data through natural language questions. Built using **AWS Bedrock** (Claude Sonnet) and the **Strands Agent SDK**.

**Example interactions:**
- "Give me an overview of my transactions"
- "Why are my cards getting declined?"
- "When will I get my next deposit?"
- "Break down my fees by card type"

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LOCAL / EC2                              │
│                                                                 │
│   ┌─────────────┐      ┌─────────────────────────────────┐     │
│   │             │      │         Strands Agent           │     │
│   │  Streamlit  │      │                                 │     │
│   │     UI      │─────→│  ┌─────────────────────────┐   │     │
│   │             │      │  │   Tool: get_summary     │   │     │
│   │  (React-    │      │  │   Tool: get_declines    │   │     │
│   │   like)     │      │  │   Tool: get_settlements │   │     │
│   │             │      │  │   Tool: analyze_cards   │   │     │
│   └─────────────┘      │  └───────────┬─────────────┘   │     │
│                        │              │                  │     │
│                        └──────────────┼──────────────────┘     │
│                                       │                         │
└───────────────────────────────────────┼─────────────────────────┘
                                        │
                                        │ API Call
                                        ▼
                        ┌───────────────────────────────┐
                        │         AWS BEDROCK           │
                        │                               │
                        │      Claude Sonnet 4          │
                        │                               │
                        │  - Understands question       │
                        │  - Decides which tool to call │
                        │  - Interprets results         │
                        │  - Generates response         │
                        │                               │
                        └───────────────────────────────┘
```

---

## How It Works

### Step-by-Step Flow

| Step | Location | What Happens |
|------|----------|--------------|
| 1 | Browser | Merchant asks: "Why are my cards getting declined?" |
| 2 | Streamlit | Question sent to Strands Agent |
| 3 | Bedrock | Claude Sonnet receives question + list of available tools |
| 4 | Bedrock | Claude decides: "I should call `get_decline_analysis()`" |
| 5 | Local | Strands executes the tool, queries transaction data |
| 6 | Local | Tool returns: `{declines: 2, reasons: {insufficient_funds: 1, expired_card: 1}}` |
| 7 | Bedrock | Claude interprets the data and writes a helpful response |
| 8 | Browser | Merchant sees: "You have a 10% decline rate. 2 transactions failed..." |

### The Magic: Tool Selection

The LLM **automatically decides** which tool to use based on the question. No if/else logic required.

```python
# Define a tool
@tool
def get_decline_analysis(merchant_id: str) -> str:
    """Analyze declined transactions and reasons."""
    # Query data, return JSON
    return json.dumps(results)

# Create agent with tools
agent = Agent(
    model="us.anthropic.claude-sonnet-4-20250514-v1:0",
    tools=[get_decline_analysis, get_transaction_summary, ...],
    system_prompt="You help merchants understand their payments..."
)

# Ask anything - Claude picks the right tool
response = agent("Why are my cards getting declined?")
```

---

## Available Tools

| Tool | Purpose | Sample Output |
|------|---------|---------------|
| `get_transaction_summary` | Overview metrics | Volume, counts, fees, decline rate |
| `get_transactions_by_status` | Filter by status | List of settled/pending/declined txns |
| `get_settlement_details` | Payout information | Deposit amounts, dates, fees |
| `analyze_card_types` | Card breakdown | Volume/fees by Visa, MC, Amex, etc. |
| `get_decline_analysis` | Decline reasons | Why cards are failing |
| `compare_periods` | Period comparison | This week vs last week |

---

## Demo Screenshots

### Dashboard View
- Gross volume, net deposits, transaction count
- Decline rate metric
- Charts: status breakdown, volume by card type
- Settlement history timeline

### "Ask Your Data" View
- Natural language input
- Example prompts as clickable buttons
- AI-generated insights with real data
- Chat history

### Settlements View
- Total deposited vs pending
- Fee breakdown
- Detailed settlement table

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| LLM | Claude Sonnet 4 (Bedrock) | Reasoning, tool selection, response generation |
| Agent Framework | Strands SDK | Tool orchestration, Bedrock integration |
| Frontend | Streamlit | Rapid UI development |
| Hosting | EC2 + CloudFront | Production deployment |
| IaC | AWS CDK (JavaScript) | Infrastructure as code |

---

## Why This Approach?

### vs. Traditional Dashboard
| Traditional | AI Agent |
|-------------|----------|
| Predefined charts only | Ask any question |
| User finds insights | Insights come to user |
| Requires training | Natural language |
| Static views | Dynamic analysis |

### vs. ChatGPT/Generic AI
| Generic AI | Our Agent |
|------------|-----------|
| No access to real data | Queries actual transactions |
| Hallucinated numbers | Real metrics from database |
| Generic advice | Merchant-specific insights |
| No actions | Can trigger workflows |

---

## Roadmap

### Phase 1: Transaction Insights (Current)
- Overview metrics
- Decline analysis
- Card type breakdown
- Settlement details

### Phase 2: Settlement/Payout Agent
- "When will I get paid?"
- "Why is this deposit less than expected?"
- Reconciliation assistance

### Phase 3: Chargeback Assistant
- "Help me respond to this dispute"
- Evidence suggestions
- Win rate optimization

### Phase 4: Integration Helper
- API documentation search
- Code examples
- Error debugging

### Phase 5: Fee Analyzer
- Fee breakdown
- Cost optimization suggestions
- Pricing plan comparison

---

## Running the Demo

### Prerequisites
- AWS credentials with Bedrock access
- Python 3.11+
- Claude Sonnet 4 enabled in Bedrock

### Local Setup
```bash
# Navigate to project
cd ~/Mine/strands-agent-app

# Activate environment
source venv/bin/activate

# Run with AWS profile
AWS_PROFILE=dev streamlit run app.py
```

### Access
Open http://localhost:8501

---

## Key Takeaways

1. **Natural Language Interface** - Merchants ask questions in plain English
2. **Real Data** - Agent queries actual transaction data, no hallucinations
3. **Extensible** - Add new tools without changing the core agent
4. **AWS Native** - Bedrock for LLM, EC2/CloudFront for hosting
5. **Rapid Development** - Strands SDK + Streamlit = quick iteration

---

## Questions?

- **Code Location:** `~/Mine/strands-agent-app/`
- **Main Files:** `agent.py` (AI logic), `app.py` (UI)
- **Data:** `data/merchant-insights/` (sample transactions)
