"""
CloudWatch Agent - AWS monitoring and metrics
Tools for querying CloudWatch logs, metrics, and alarms.
"""

import os

from strands import Agent, tool
from strands.models import BedrockModel

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# ============================================================================
# TOOLS
# ============================================================================


@tool
def list_log_groups(prefix: str = "/aws/lambda", limit: int = 50) -> str:
    """List CloudWatch log groups.

    Args:
        prefix: Filter by log group prefix
        limit: Maximum number of log groups to return
    """
    # TODO: Implement CloudWatch API call
    return "TODO: Implement list_log_groups"


@tool
def query_logs(log_group: str, query: str, hours_back: int = 1, limit: int = 100) -> str:
    """Query CloudWatch logs using Logs Insights.

    Args:
        log_group: Log group name or pattern
        query: CloudWatch Logs Insights query
        hours_back: How far back to search
        limit: Maximum number of results
    """
    # TODO: Implement CloudWatch Logs Insights query
    return "TODO: Implement query_logs"


@tool
def get_log_events(log_group: str, log_stream: str = "", hours_back: int = 1, filter_pattern: str = "") -> str:
    """Get log events from a specific log group/stream.

    Args:
        log_group: Log group name
        log_stream: Specific log stream (optional)
        hours_back: How far back to search
        filter_pattern: CloudWatch filter pattern
    """
    # TODO: Implement CloudWatch API call
    return "TODO: Implement get_log_events"


@tool
def get_metric_statistics(
    namespace: str, metric_name: str, dimensions: str = "", hours_back: int = 1, statistic: str = "Average"
) -> str:
    """Get CloudWatch metric statistics.

    Args:
        namespace: Metric namespace (e.g., 'AWS/Lambda', 'AWS/RDS')
        metric_name: Name of the metric
        dimensions: Comma-separated key=value pairs (e.g., 'FunctionName=my-func')
        hours_back: How far back to query
        statistic: Statistic type - Average, Sum, Minimum, Maximum, SampleCount
    """
    # TODO: Implement CloudWatch API call
    return "TODO: Implement get_metric_statistics"


@tool
def list_alarms(state: str = "all", alarm_prefix: str = "") -> str:
    """List CloudWatch alarms and their status.

    Args:
        state: Filter by state - OK, ALARM, INSUFFICIENT_DATA, or 'all'
        alarm_prefix: Filter by alarm name prefix
    """
    # TODO: Implement CloudWatch API call
    return "TODO: Implement list_alarms"


@tool
def get_lambda_metrics(function_name: str, hours_back: int = 24) -> str:
    """Get key metrics for a Lambda function (invocations, errors, duration).

    Args:
        function_name: Lambda function name
        hours_back: How far back to query
    """
    # TODO: Implement CloudWatch API call
    return "TODO: Implement get_lambda_metrics"


@tool
def get_rds_metrics(db_instance: str, hours_back: int = 24) -> str:
    """Get key metrics for an RDS instance (CPU, connections, storage).

    Args:
        db_instance: RDS instance identifier
        hours_back: How far back to query
    """
    # TODO: Implement CloudWatch API call
    return "TODO: Implement get_rds_metrics"


# Export tools list
CLOUDWATCH_TOOLS = [
    list_log_groups,
    query_logs,
    get_log_events,
    get_metric_statistics,
    list_alarms,
    get_lambda_metrics,
    get_rds_metrics,
]

# System prompt
SYSTEM_PROMPT = """You are a CloudWatch Monitoring Assistant for MrRobot's AWS infrastructure.

You help the team with:
- Querying and analyzing CloudWatch logs
- Monitoring metrics for Lambda, RDS, and other services
- Checking alarm status and health
- Investigating performance issues

AVAILABLE TOOLS:
1. list_log_groups - List available log groups
2. query_logs - Run Logs Insights queries
3. get_log_events - Get raw log events
4. get_metric_statistics - Query any CloudWatch metric
5. list_alarms - Check alarm status
6. get_lambda_metrics - Lambda-specific metrics summary
7. get_rds_metrics - RDS-specific metrics summary

When investigating issues:
1. Start with relevant log groups
2. Use Logs Insights for complex queries
3. Correlate with metrics when needed
4. Check alarms for known issues
"""


# Create agent
def create_cloudwatch_agent():
    model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-west-2")
    return Agent(model=model, tools=CLOUDWATCH_TOOLS, system_prompt=SYSTEM_PROMPT)


cloudwatch_agent = None  # Lazy initialization
