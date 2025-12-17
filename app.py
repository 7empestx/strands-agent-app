"""
MrRobot DevOps Dashboard
AI-Powered Operations Hub for Security, Logs, and Business Insights
Powered by Strands Agent + Claude Sonnet on Bedrock
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime

# Import the agents
from agents.transaction_agent import run_agent, DATASETS
from agents.vulnerability_agent import run_vulnerability_agent, VULNERABILITIES
from agents.coralogix_agent import run_coralogix_agent, KNOWN_SERVICES, CORALOGIX_API_KEY
from agents.devops_agent import create_devops_agent, DEVOPS_TOOLS

# Page config
st.set_page_config(
    page_title="MrRobot DevOps Hub",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
    }
    .stMetric > div {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []


def load_transaction_data():
    """Load transaction data."""
    transactions = DATASETS.get("transactions", [])
    return pd.DataFrame(transactions) if transactions else pd.DataFrame()


def load_settlement_data():
    """Load settlement data."""
    settlements = DATASETS.get("settlements", [])
    return pd.DataFrame(settlements) if settlements else pd.DataFrame()


def show_dashboard():
    """Show the main transaction dashboard."""
    st.header("Transaction Overview")

    txn_df = load_transaction_data()
    stl_df = load_settlement_data()

    if txn_df.empty:
        st.warning("No transaction data available")
        return

    # Calculate metrics
    sales = txn_df[txn_df['transaction_type'] == 'sale']
    settled = sales[sales['status'] == 'settled']
    declined = sales[sales['status'] == 'declined']
    pending = txn_df[txn_df['status'] == 'pending']

    # Metrics row
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Gross Volume",
            f"${sales['amount'].sum():,.2f}",
            help="Total sales attempted"
        )

    with col2:
        st.metric(
            "Net Deposited",
            f"${settled['net_amount'].sum():,.2f}",
            help="After fees, refunds, chargebacks"
        )

    with col3:
        st.metric(
            "Transactions",
            len(sales),
            f"{len(settled)} settled"
        )

    with col4:
        decline_rate = (len(declined) / len(sales) * 100) if len(sales) > 0 else 0
        st.metric(
            "Decline Rate",
            f"{decline_rate:.1f}%",
            help="Percentage of declined transactions"
        )

    with col5:
        st.metric(
            "Total Fees",
            f"${txn_df['fee'].sum():,.2f}",
            help="Processing fees paid"
        )

    # Charts row
    st.subheader("Analytics")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        # Transaction status breakdown
        status_counts = txn_df['status'].value_counts()
        fig = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title="Transactions by Status",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        # Card type breakdown
        card_volumes = sales.groupby('card_type')['amount'].sum().sort_values(ascending=True)
        fig = px.bar(
            x=card_volumes.values,
            y=card_volumes.index,
            orientation='h',
            title="Volume by Card Type",
            labels={'x': 'Volume ($)', 'y': 'Card Type'}
        )
        fig.update_traces(marker_color='#667eea')
        st.plotly_chart(fig, use_container_width=True)

    # Settlement timeline
    if not stl_df.empty:
        st.subheader("Settlement History")
        stl_df['settlement_date'] = pd.to_datetime(stl_df['settlement_date'])
        fig = px.bar(
            stl_df,
            x='settlement_date',
            y='net_amount',
            title="Daily Settlements",
            labels={'net_amount': 'Net Amount ($)', 'settlement_date': 'Date'},
            color='status',
            color_discrete_map={'deposited': '#28a745', 'pending': '#ffc107'}
        )
        st.plotly_chart(fig, use_container_width=True)

    # Recent transactions table
    st.subheader("Recent Transactions")
    display_df = txn_df[['transaction_id', 'amount', 'status', 'card_type', 'created_at', 'fee', 'net_amount']].copy()
    display_df['amount'] = display_df['amount'].apply(lambda x: f"${x:,.2f}")
    display_df['fee'] = display_df['fee'].apply(lambda x: f"${x:,.2f}")
    display_df['net_amount'] = display_df['net_amount'].apply(lambda x: f"${x:,.2f}")
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def show_insights_agent():
    """Show the AI insights agent chat interface."""
    st.header("Ask Your Data")
    st.write("Get instant insights about your transactions, settlements, and business performance.")

    # Example prompts
    st.write("**Try asking:**")
    examples = [
        "Give me an overview of my transactions",
        "What's my decline rate and why are cards being declined?",
        "Break down my volume by card type",
        "When will I get my next deposit?",
        "How do this week's sales compare to last week?"
    ]

    # Create clickable example buttons
    cols = st.columns(3)
    for i, example in enumerate(examples[:3]):
        with cols[i]:
            if st.button(example, key=f"ex_{i}", use_container_width=True):
                st.session_state.current_prompt = example

    cols2 = st.columns(2)
    for i, example in enumerate(examples[3:]):
        with cols2[i]:
            if st.button(example, key=f"ex2_{i}", use_container_width=True):
                st.session_state.current_prompt = example

    st.divider()

    # Chat input
    user_input = st.text_area(
        "Your question:",
        value=st.session_state.get('current_prompt', ''),
        placeholder="Ask anything about your transactions...",
        height=80
    )

    if st.button("Get Insights", type="primary", use_container_width=True):
        if user_input:
            with st.spinner("Analyzing your data..."):
                try:
                    response = run_agent(user_input)

                    # Store in history
                    st.session_state.chat_history.append({
                        "user": user_input,
                        "agent": response,
                        "timestamp": datetime.now().strftime("%I:%M %p")
                    })

                    st.session_state.current_prompt = ''

                except Exception as e:
                    st.error(f"Error: {e}")

    # Display response
    if st.session_state.chat_history:
        latest = st.session_state.chat_history[-1]

        st.subheader("Insights")
        st.info(f"**You asked:** {latest['user']}")
        st.write(latest['agent'])

    # Chat history
    if len(st.session_state.chat_history) > 1:
        with st.expander("Previous Questions"):
            for chat in reversed(st.session_state.chat_history[:-1]):
                st.markdown(f"**{chat['timestamp']}** - {chat['user'][:60]}...")
                st.caption(chat['agent'][:200] + "..." if len(chat['agent']) > 200 else chat['agent'])
                st.divider()

    if st.session_state.chat_history:
        if st.button("Clear History"):
            st.session_state.chat_history = []
            st.rerun()


def show_settlements():
    """Show settlement details page."""
    st.header("Settlements & Payouts")

    stl_df = load_settlement_data()

    if stl_df.empty:
        st.warning("No settlement data available")
        return

    # Summary metrics
    deposited = stl_df[stl_df['status'] == 'deposited']
    pending = stl_df[stl_df['status'] == 'pending']

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Deposited", f"${deposited['net_amount'].sum():,.2f}")

    with col2:
        st.metric("Pending", f"${pending['net_amount'].sum():,.2f}")

    with col3:
        st.metric("Total Fees", f"${stl_df['total_fees'].sum():,.2f}")

    with col4:
        st.metric("Chargebacks", f"${stl_df['chargebacks'].sum():,.2f}")

    # Settlement table
    st.subheader("Settlement Details")

    display_df = stl_df.copy()
    for col in ['gross_amount', 'total_fees', 'chargebacks', 'refunds', 'net_amount']:
        display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)


def show_vulnerability_dashboard():
    """Show vulnerability overview dashboard."""
    st.header("Security Vulnerabilities")

    df = pd.DataFrame(VULNERABILITIES)

    if df.empty:
        st.warning("No vulnerability data available. Add npm audit JSON files to data/npm-audits/")
        st.info("Run: `npm audit --json > data/npm-audits/<repo-name>.json`")
        return

    # Key metrics row
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Total Vulnerabilities",
            len(df),
            help="All vulnerabilities across repos"
        )

    with col2:
        critical = len(df[df['severity'] == 'critical'])
        st.metric(
            "Critical",
            critical,
            delta=f"-{critical}" if critical > 0 else None,
            delta_color="inverse",
            help="Requires immediate action"
        )

    with col3:
        high = len(df[df['severity'] == 'high'])
        st.metric(
            "High",
            high,
            help="Fix within days"
        )

    with col4:
        fixable = df['fix_available'].sum()
        fix_rate = (fixable / len(df) * 100) if len(df) > 0 else 0
        st.metric(
            "Fixable",
            f"{int(fixable)} ({fix_rate:.0f}%)",
            help="Vulnerabilities with available updates"
        )

    with col5:
        repos = df['repo'].nunique()
        st.metric(
            "Repositories",
            repos,
            help="Number of repos being tracked"
        )

    # Charts row
    st.subheader("Overview")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        # Severity breakdown
        severity_counts = df['severity'].value_counts()
        severity_order = ['critical', 'high', 'moderate', 'low', 'info']
        severity_counts = severity_counts.reindex(severity_order, fill_value=0)

        fig = px.bar(
            x=severity_counts.values,
            y=severity_counts.index,
            orientation='h',
            title="Vulnerabilities by Severity",
            labels={'x': 'Count', 'y': 'Severity'},
            color=severity_counts.index,
            color_discrete_map={
                'critical': '#dc3545',
                'high': '#fd7e14',
                'moderate': '#ffc107',
                'low': '#20c997',
                'info': '#6c757d'
            }
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        # Top vulnerable packages
        top_packages = df['package'].value_counts().head(10)
        fig = px.bar(
            x=top_packages.values,
            y=top_packages.index,
            orientation='h',
            title="Most Vulnerable Packages",
            labels={'x': 'Vulnerability Count', 'y': 'Package'}
        )
        fig.update_traces(marker_color='#667eea')
        st.plotly_chart(fig, use_container_width=True)

    # Repository breakdown
    st.subheader("Repository Status")
    repo_summary = []
    for repo in df['repo'].unique():
        repo_df = df[df['repo'] == repo]
        repo_summary.append({
            'Repository': repo,
            'Total': len(repo_df),
            'Critical': len(repo_df[repo_df['severity'] == 'critical']),
            'High': len(repo_df[repo_df['severity'] == 'high']),
            'Moderate': len(repo_df[repo_df['severity'] == 'moderate']),
            'Fixable': int(repo_df['fix_available'].sum())
        })

    repo_df = pd.DataFrame(repo_summary).sort_values(['Critical', 'High'], ascending=False)
    st.dataframe(repo_df, use_container_width=True, hide_index=True)

    # Critical vulnerabilities table
    critical_df = df[df['severity'].isin(['critical', 'high'])].copy()
    if not critical_df.empty:
        st.subheader("Critical & High Priority Vulnerabilities")

        display_df = critical_df[['repo', 'package', 'severity', 'advisory_title', 'fix_available', 'fix_version']].copy()
        display_df['fix_available'] = display_df['fix_available'].map({True: 'Yes', False: 'No'})
        display_df.columns = ['Repository', 'Package', 'Severity', 'Advisory', 'Fix Available', 'Fix Version']

        st.dataframe(
            display_df.sort_values(['Severity', 'Repository']),
            use_container_width=True,
            hide_index=True
        )


def show_security_agent():
    """Show the security agent chat interface."""
    st.header("Security Assistant")
    st.write("Ask questions about vulnerabilities across your repositories.")

    # Initialize session state for vulnerability chat
    if 'vuln_chat_history' not in st.session_state:
        st.session_state.vuln_chat_history = []

    # Example prompts
    st.write("**Try asking:**")
    examples = [
        "What's my overall security posture?",
        "Show me critical vulnerabilities across all repos",
        "What vulnerabilities does lodash have?",
        "Give me a remediation plan for frontend-app",
        "Which repos have the most critical issues?"
    ]

    cols = st.columns(3)
    for i, example in enumerate(examples[:3]):
        with cols[i]:
            if st.button(example, key=f"vuln_ex_{i}", use_container_width=True):
                st.session_state.vuln_prompt = example

    cols2 = st.columns(2)
    for i, example in enumerate(examples[3:]):
        with cols2[i]:
            if st.button(example, key=f"vuln_ex2_{i}", use_container_width=True):
                st.session_state.vuln_prompt = example

    st.divider()

    # Chat input
    user_input = st.text_area(
        "Your question:",
        value=st.session_state.get('vuln_prompt', ''),
        placeholder="Ask about vulnerabilities, packages, or repos...",
        height=80
    )

    if st.button("Ask Security Assistant", type="primary", use_container_width=True):
        if user_input:
            with st.spinner("Analyzing security data..."):
                try:
                    response = run_vulnerability_agent(user_input)

                    st.session_state.vuln_chat_history.append({
                        "user": user_input,
                        "agent": response,
                        "timestamp": datetime.now().strftime("%I:%M %p")
                    })

                    st.session_state.vuln_prompt = ''

                except Exception as e:
                    st.error(f"Error: {e}")

    # Display response
    if st.session_state.vuln_chat_history:
        latest = st.session_state.vuln_chat_history[-1]

        st.subheader("Response")
        st.info(f"**You asked:** {latest['user']}")
        st.write(latest['agent'])

    # Chat history
    if len(st.session_state.vuln_chat_history) > 1:
        with st.expander("Previous Questions"):
            for chat in reversed(st.session_state.vuln_chat_history[:-1]):
                st.markdown(f"**{chat['timestamp']}** - {chat['user'][:60]}...")
                st.caption(chat['agent'][:200] + "..." if len(chat['agent']) > 200 else chat['agent'])
                st.divider()

    if st.session_state.vuln_chat_history:
        if st.button("Clear Security History"):
            st.session_state.vuln_chat_history = []
            st.rerun()


def show_coralogix_agent():
    """Show the Coralogix log analysis agent interface."""
    st.header("Log Analysis Agent")
    st.write("Query and analyze logs from all services in Coralogix - Cast services, Lambda functions, and more.")

    # Initialize session state for coralogix chat
    if 'coralogix_chat_history' not in st.session_state:
        st.session_state.coralogix_chat_history = []

    # Check for API key
    if not CORALOGIX_API_KEY:
        st.error("CORALOGIX_AGENT_KEY environment variable not set")
        st.info("Set it with: `export CORALOGIX_AGENT_KEY='your-api-key'`")
        st.write("You need a Personal Key with DataQuerying permission from Coralogix Settings > API Keys")
        return

    # Show known services
    with st.expander("Known Services (auto-detected from logs)"):
        st.write("The agent can discover all services automatically. Known patterns include:")
        cast_services = [k for k, v in KNOWN_SERVICES.items() if 'cast' in k]
        other_services = [k for k, v in KNOWN_SERVICES.items() if 'cast' not in k]

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Cast Services:**")
            for svc in cast_services:
                st.write(f"- {svc}")
        with col2:
            st.write("**Other Services:**")
            for svc in other_services:
                st.write(f"- {svc}")

    # Example prompts
    st.write("**Try asking:**")
    examples = [
        "Show me cast-core prod errors",
        "Health check for prod services",
        "How many errors in the last 4 hours?",
        "What services are logging?",
        "Search for 'timeout' in prod logs",
        "Compare error rates across environments"
    ]

    cols = st.columns(3)
    for i, example in enumerate(examples[:3]):
        with cols[i]:
            if st.button(example, key=f"cx_ex_{i}", use_container_width=True):
                st.session_state.coralogix_prompt = example

    cols2 = st.columns(3)
    for i, example in enumerate(examples[3:]):
        with cols2[i]:
            if st.button(example, key=f"cx_ex2_{i}", use_container_width=True):
                st.session_state.coralogix_prompt = example

    st.divider()

    # Chat input
    user_input = st.text_area(
        "Your question:",
        value=st.session_state.get('coralogix_prompt', ''),
        placeholder="Ask about logs, errors, services, health...",
        height=80
    )

    if st.button("Query Logs", type="primary", use_container_width=True):
        if user_input:
            with st.spinner("Querying Coralogix..."):
                try:
                    response = run_coralogix_agent(user_input)

                    st.session_state.coralogix_chat_history.append({
                        "user": user_input,
                        "agent": response,
                        "timestamp": datetime.now().strftime("%I:%M %p")
                    })

                    st.session_state.coralogix_prompt = ''

                except Exception as e:
                    st.error(f"Error: {e}")

    # Display response
    if st.session_state.coralogix_chat_history:
        latest = st.session_state.coralogix_chat_history[-1]

        st.subheader("Response")
        st.info(f"**You asked:** {latest['user']}")
        st.write(latest['agent'])

    # Chat history
    if len(st.session_state.coralogix_chat_history) > 1:
        with st.expander("Previous Questions"):
            for chat in reversed(st.session_state.coralogix_chat_history[:-1]):
                st.markdown(f"**{chat['timestamp']}** - {chat['user'][:60]}...")
                st.caption(chat['agent'][:200] + "..." if len(chat['agent']) > 200 else chat['agent'])
                st.divider()

    if st.session_state.coralogix_chat_history:
        if st.button("Clear Log History"):
            st.session_state.coralogix_chat_history = []
            st.rerun()


def show_devops_agent():
    """Show the DevOps orchestrator agent interface."""
    st.header("DevOps Agent")
    st.write("Your AI DevOps assistant that orchestrates specialized agents to answer complex cross-system queries.")
    st.caption("**READ-ONLY** - This agent queries and analyzes but never modifies anything.")

    # Initialize session state for devops chat
    if 'devops_chat_history' not in st.session_state:
        st.session_state.devops_chat_history = []

    # Show available tools
    with st.expander("Available Capabilities"):
        st.markdown("""
**Tools this agent can use:**

| Tool | Description |
|------|-------------|
| `query_coralogix` | Ask the Coralogix agent any log-related question |
| `list_available_agents` | See all agents and their status |
| `get_system_overview` | Quick health summary across systems |
| `investigate_service` | Deep dive into a specific service |
| `search_across_systems` | Search for patterns everywhere |
| `compare_environments` | Compare service across prod/dev/staging |

**Connected Agents:**
- Coralogix Log Analysis Agent (Active)
- CloudWatch Agent (Placeholder)
- Bitbucket Agent (Placeholder)
- Confluence Agent (Placeholder)
- Database Agent (Placeholder)
- Risk Agent (Placeholder)
        """)

    # Example prompts
    st.write("**Try asking:**")
    examples = [
        "What's wrong with cast-core?",
        "Show me a system overview",
        "Search for timeout errors",
        "Compare cast-core across environments",
        "List available agents",
        "Investigate payment-service in prod"
    ]

    cols = st.columns(3)
    for i, example in enumerate(examples[:3]):
        with cols[i]:
            if st.button(example, key=f"devops_ex_{i}", use_container_width=True):
                st.session_state.devops_prompt = example

    cols2 = st.columns(3)
    for i, example in enumerate(examples[3:]):
        with cols2[i]:
            if st.button(example, key=f"devops_ex2_{i}", use_container_width=True):
                st.session_state.devops_prompt = example

    st.divider()

    # Chat input
    user_input = st.text_area(
        "Your question:",
        value=st.session_state.get('devops_prompt', ''),
        placeholder="Ask about services, logs, errors, health, comparisons...",
        height=80
    )

    if st.button("Ask DevOps Agent", type="primary", use_container_width=True):
        if user_input:
            with st.spinner("Coordinating agents and gathering data..."):
                try:
                    # Create the agent and run the query
                    devops_agent = create_devops_agent()
                    result = devops_agent(user_input)

                    # Extract the response text from the agent result
                    response = ""
                    if hasattr(result, 'message'):
                        msg = result.message
                        # Handle dict-like message structure
                        if isinstance(msg, dict):
                            content = msg.get('content', [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and 'text' in item:
                                        response += item['text']
                            else:
                                response = str(content)
                        else:
                            response = str(msg)
                    else:
                        response = str(result)

                    if not response:
                        response = "No response received from agent"

                    st.session_state.devops_chat_history.append({
                        "user": user_input,
                        "agent": response,
                        "timestamp": datetime.now().strftime("%I:%M %p")
                    })

                    st.session_state.devops_prompt = ''

                except Exception as e:
                    st.error(f"Error: {e}")

    # Display response
    if st.session_state.devops_chat_history:
        latest = st.session_state.devops_chat_history[-1]

        st.subheader("Response")
        st.info(f"**You asked:** {latest['user']}")
        st.write(latest['agent'])

    # Chat history
    if len(st.session_state.devops_chat_history) > 1:
        with st.expander("Previous Questions"):
            for chat in reversed(st.session_state.devops_chat_history[:-1]):
                st.markdown(f"**{chat['timestamp']}** - {chat['user'][:60]}...")
                st.caption(chat['agent'][:200] + "..." if len(chat['agent']) > 200 else chat['agent'])
                st.divider()

    if st.session_state.devops_chat_history:
        if st.button("Clear DevOps History"):
            st.session_state.devops_chat_history = []
            st.rerun()


def main():
    # Sidebar
    st.sidebar.title("MrRobot DevOps Hub")
    st.sidebar.caption("AI-Powered Operations")

    st.sidebar.divider()

    # Navigation with sections
    st.sidebar.subheader("Operations")
    page = st.sidebar.radio(
        "Navigate",
        [
            "DevOps Agent",
            "Log Analysis",
            "Security Vulnerabilities",
            "Security Assistant",
            "Transaction Dashboard",
            "Business Insights",
            "Settlements"
        ],
        label_visibility="collapsed"
    )

    # Status
    st.sidebar.divider()
    st.sidebar.caption("**Agent Status**")
    try:
        from agents.transaction_agent import agent
        st.sidebar.success("Claude Sonnet")
    except Exception as e:
        st.sidebar.error("Agent offline")

    # Coralogix status
    if CORALOGIX_API_KEY:
        st.sidebar.success("Coralogix")
    else:
        st.sidebar.warning("Coralogix: No API Key")

    st.sidebar.caption(f"Region: {os.environ.get('AWS_REGION', 'us-east-1')}")

    # Main content - page routing
    if page == "DevOps Agent":
        show_devops_agent()
    elif page == "Log Analysis":
        show_coralogix_agent()
    elif page == "Security Vulnerabilities":
        show_vulnerability_dashboard()
    elif page == "Security Assistant":
        show_security_agent()
    elif page == "Transaction Dashboard":
        show_dashboard()
    elif page == "Business Insights":
        show_insights_agent()
    elif page == "Settlements":
        show_settlements()


if __name__ == "__main__":
    main()
