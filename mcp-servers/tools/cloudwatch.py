"""CloudWatch Observability tools for MCP server.

Provides tools for CloudWatch metrics, alarms, and log insights.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.aws import get_session


def _get_cloudwatch_client():
    """Get CloudWatch client."""
    return get_session().client("cloudwatch")


def _get_logs_client():
    """Get CloudWatch Logs client."""
    return get_session().client("logs")


# ============================================================================
# CLOUDWATCH METRICS
# ============================================================================


def get_metric_statistics(
    namespace: str,
    metric_name: str,
    dimensions: list = None,
    period: int = 300,
    hours_back: int = 1,
    statistics: list = None,
) -> dict:
    """Get CloudWatch metric statistics.

    Args:
        namespace: CloudWatch namespace (e.g., 'AWS/ECS', 'AWS/Lambda')
        metric_name: Metric name (e.g., 'CPUUtilization')
        dimensions: List of dimension dicts [{"Name": "...", "Value": "..."}]
        period: Period in seconds (default: 300 = 5 min)
        hours_back: Hours of data to retrieve
        statistics: List of statistics ['Average', 'Maximum', 'Minimum', 'Sum']

    Returns:
        dict with metric datapoints or error
    """
    client = _get_cloudwatch_client()

    if statistics is None:
        statistics = ["Average", "Maximum", "Minimum"]

    if dimensions is None:
        dimensions = []

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours_back)

    try:
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=statistics,
        )

        datapoints = []
        for dp in sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"]):
            datapoints.append({
                "timestamp": dp["Timestamp"].isoformat(),
                "average": dp.get("Average"),
                "maximum": dp.get("Maximum"),
                "minimum": dp.get("Minimum"),
                "sum": dp.get("Sum"),
                "unit": dp.get("Unit"),
            })

        return {
            "namespace": namespace,
            "metric_name": metric_name,
            "dimensions": dimensions,
            "period_seconds": period,
            "datapoints": datapoints,
            "count": len(datapoints),
        }
    except Exception as e:
        return {"error": str(e)}


def list_alarms(state_value: str = None, alarm_name_prefix: str = None) -> dict:
    """List CloudWatch alarms.

    Args:
        state_value: Filter by state ('OK', 'ALARM', 'INSUFFICIENT_DATA')
        alarm_name_prefix: Filter by alarm name prefix

    Returns:
        dict with alarms list or error
    """
    client = _get_cloudwatch_client()

    try:
        params = {}
        if state_value:
            params["StateValue"] = state_value
        if alarm_name_prefix:
            params["AlarmNamePrefix"] = alarm_name_prefix

        response = client.describe_alarms(**params)

        alarms = []
        for alarm in response.get("MetricAlarms", []):
            alarms.append({
                "name": alarm.get("AlarmName"),
                "state": alarm.get("StateValue"),
                "state_reason": alarm.get("StateReason", "")[:200],
                "metric": alarm.get("MetricName"),
                "namespace": alarm.get("Namespace"),
                "threshold": alarm.get("Threshold"),
                "comparison": alarm.get("ComparisonOperator"),
                "updated": alarm.get("StateUpdatedTimestamp", "").isoformat() if alarm.get("StateUpdatedTimestamp") else None,
            })

        return {
            "alarms": alarms,
            "count": len(alarms),
            "filter": {"state": state_value, "prefix": alarm_name_prefix},
        }
    except Exception as e:
        return {"error": str(e)}


def get_alarm_history(alarm_name: str, hours_back: int = 24) -> dict:
    """Get history for a specific CloudWatch alarm.

    Args:
        alarm_name: Name of the alarm
        hours_back: Hours of history to retrieve

    Returns:
        dict with alarm history or error
    """
    client = _get_cloudwatch_client()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours_back)

    try:
        response = client.describe_alarm_history(
            AlarmName=alarm_name,
            StartDate=start_time,
            EndDate=end_time,
            HistoryItemType="StateUpdate",
            MaxRecords=50,
        )

        history = []
        for item in response.get("AlarmHistoryItems", []):
            history.append({
                "timestamp": item.get("Timestamp", "").isoformat() if item.get("Timestamp") else None,
                "type": item.get("HistoryItemType"),
                "summary": item.get("HistorySummary"),
            })

        return {
            "alarm_name": alarm_name,
            "history": history,
            "count": len(history),
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# CLOUDWATCH LOGS
# ============================================================================


def list_log_groups(prefix: str = None, limit: int = 50) -> dict:
    """List CloudWatch Log Groups.

    Args:
        prefix: Filter by log group name prefix
        limit: Maximum log groups to return

    Returns:
        dict with log groups or error
    """
    client = _get_logs_client()

    try:
        params = {"limit": limit}
        if prefix:
            params["logGroupNamePrefix"] = prefix

        response = client.describe_log_groups(**params)

        groups = []
        for group in response.get("logGroups", []):
            groups.append({
                "name": group.get("logGroupName"),
                "stored_bytes": group.get("storedBytes", 0),
                "retention_days": group.get("retentionInDays"),
                "created": datetime.fromtimestamp(
                    group.get("creationTime", 0) / 1000, tz=timezone.utc
                ).isoformat() if group.get("creationTime") else None,
            })

        return {
            "log_groups": groups,
            "count": len(groups),
            "prefix_filter": prefix,
        }
    except Exception as e:
        return {"error": str(e)}


def query_logs(
    log_group: str,
    query: str = "fields @timestamp, @message | sort @timestamp desc | limit 50",
    hours_back: int = 1,
) -> dict:
    """Run CloudWatch Logs Insights query.

    Args:
        log_group: Log group name
        query: Logs Insights query string
        hours_back: Hours of logs to search

    Returns:
        dict with query results or error
    """
    client = _get_logs_client()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours_back)

    try:
        # Start the query
        response = client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query,
        )
        query_id = response["queryId"]

        # Wait for query to complete (with timeout)
        import time
        for _ in range(30):  # Max 30 seconds
            result = client.get_query_results(queryId=query_id)
            status = result.get("status")
            if status == "Complete":
                break
            elif status in ["Failed", "Cancelled"]:
                return {"error": f"Query {status}"}
            time.sleep(1)

        # Parse results
        results = []
        for row in result.get("results", []):
            entry = {}
            for field in row:
                entry[field["field"]] = field["value"]
            results.append(entry)

        return {
            "log_group": log_group,
            "query": query,
            "results": results,
            "count": len(results),
            "statistics": result.get("statistics", {}),
        }
    except Exception as e:
        return {"error": str(e)}


def get_ecs_service_metrics(cluster_name: str, service_name: str, hours_back: int = 1) -> dict:
    """Get ECS service CPU and memory metrics.

    Args:
        cluster_name: ECS cluster name
        service_name: ECS service name
        hours_back: Hours of data to retrieve

    Returns:
        dict with CPU and memory metrics or error
    """
    dimensions = [
        {"Name": "ClusterName", "Value": cluster_name},
        {"Name": "ServiceName", "Value": service_name},
    ]

    cpu_metrics = get_metric_statistics(
        namespace="AWS/ECS",
        metric_name="CPUUtilization",
        dimensions=dimensions,
        hours_back=hours_back,
    )

    memory_metrics = get_metric_statistics(
        namespace="AWS/ECS",
        metric_name="MemoryUtilization",
        dimensions=dimensions,
        hours_back=hours_back,
    )

    return {
        "cluster": cluster_name,
        "service": service_name,
        "cpu_utilization": cpu_metrics,
        "memory_utilization": memory_metrics,
    }


def get_lambda_metrics(function_name: str, hours_back: int = 1) -> dict:
    """Get Lambda function metrics (invocations, errors, duration).

    Args:
        function_name: Lambda function name
        hours_back: Hours of data to retrieve

    Returns:
        dict with Lambda metrics or error
    """
    dimensions = [{"Name": "FunctionName", "Value": function_name}]

    invocations = get_metric_statistics(
        namespace="AWS/Lambda",
        metric_name="Invocations",
        dimensions=dimensions,
        hours_back=hours_back,
        statistics=["Sum"],
    )

    errors = get_metric_statistics(
        namespace="AWS/Lambda",
        metric_name="Errors",
        dimensions=dimensions,
        hours_back=hours_back,
        statistics=["Sum"],
    )

    duration = get_metric_statistics(
        namespace="AWS/Lambda",
        metric_name="Duration",
        dimensions=dimensions,
        hours_back=hours_back,
        statistics=["Average", "Maximum"],
    )

    return {
        "function_name": function_name,
        "invocations": invocations,
        "errors": errors,
        "duration": duration,
    }

