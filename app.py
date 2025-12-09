"""
Merchant Transaction Insights Dashboard
Powered by Strands Agent + Claude Sonnet on Bedrock
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime

# Import the agent
from agent import run_agent, DATASETS

# Page config
st.set_page_config(
    page_title="Merchant Insights",
    page_icon="💳",
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


def main():
    # Sidebar
    st.sidebar.title("💳 Merchant Portal")
    st.sidebar.write("**Coastal Coffee Roasters**")
    st.sidebar.caption("Merchant ID: merch_100")

    st.sidebar.divider()

    # Navigation
    page = st.sidebar.radio(
        "Navigate",
        ["Dashboard", "Ask Your Data", "Settlements"],
        label_visibility="collapsed"
    )

    # Status
    st.sidebar.divider()
    st.sidebar.caption("**Agent Status**")
    try:
        from agent import agent
        st.sidebar.success("✓ Connected to Claude Sonnet")
    except Exception as e:
        st.sidebar.error(f"✗ Agent offline")

    st.sidebar.caption(f"Region: {os.environ.get('AWS_REGION', 'us-east-1')}")

    # Main content
    st.title("Transaction Insights")

    if page == "Dashboard":
        show_dashboard()
    elif page == "Ask Your Data":
        show_insights_agent()
    elif page == "Settlements":
        show_settlements()


if __name__ == "__main__":
    main()
