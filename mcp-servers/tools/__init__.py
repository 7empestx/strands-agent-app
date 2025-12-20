"""MCP Tools - Modular tool definitions.

Tools are defined in separate modules and registered with FastMCP
via @mcp.tool() decorators in server.py.
"""

from .atlassian import (
    handle_add_user_to_group,
    handle_create_group,
    handle_delete_group,
    handle_get_directories,
    handle_grant_group_access,
    handle_list_groups,
    handle_list_users,
    handle_remove_user,
    handle_remove_user_from_group,
    handle_restore_user,
    handle_revoke_group_access,
    handle_suspend_user,
)
from .cloudwatch import (
    get_alarm_history,
    get_ecs_service_metrics,
    get_lambda_metrics,
    get_metric_statistics,
    list_alarms,
    list_log_groups,
    query_logs,
)

# Export handler functions for use in server.py
from .code_search import KB_ID, KNOWN_REPOS, get_file_from_bitbucket, search_knowledge_base
from .coralogix import (
    handle_discover_services,
    handle_get_recent_errors,
    handle_get_service_health,
    handle_get_service_logs,
    handle_search_logs,
)

__all__ = [
    # Code Search (Bedrock Knowledge Base)
    "search_knowledge_base",
    "get_file_from_bitbucket",
    "KNOWN_REPOS",
    "KB_ID",
    # Coralogix
    "handle_discover_services",
    "handle_get_recent_errors",
    "handle_get_service_logs",
    "handle_search_logs",
    "handle_get_service_health",
    # Atlassian
    "handle_get_directories",
    "handle_list_users",
    "handle_suspend_user",
    "handle_restore_user",
    "handle_remove_user",
    "handle_list_groups",
    "handle_create_group",
    "handle_delete_group",
    "handle_add_user_to_group",
    "handle_remove_user_from_group",
    "handle_grant_group_access",
    "handle_revoke_group_access",
    # CloudWatch
    "get_metric_statistics",
    "list_alarms",
    "get_alarm_history",
    "list_log_groups",
    "query_logs",
    "get_ecs_service_metrics",
    "get_lambda_metrics",
]
