"""Jira API tools for ticket management.

Provides functions to search, read, and manage Jira tickets.
Uses Jira Cloud REST API v3 with Basic Auth (Classic API Token).

To create a Classic API Token:
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a label and copy the token

API Reference: https://developer.atlassian.com/cloud/jira/platform/rest/v3/
"""

import base64
import os
import sys

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.lib.utils.secrets import get_secret

# Jira site configuration
JIRA_SITE = "completemerchantsolutions.atlassian.net"
JIRA_EMAIL = "gstarkman@nex.io"


def _get_jira_config() -> dict:
    """Get Jira configuration for Basic Auth with Classic API Token."""
    api_token = get_secret("JIRA_API_TOKEN")
    if not api_token:
        raise ValueError("Missing JIRA_API_TOKEN in secrets")

    # Basic Auth: base64(email:api_token)
    auth_string = f"{JIRA_EMAIL}:{api_token}"
    auth_bytes = base64.b64encode(auth_string.encode()).decode()

    return {
        "base_url": f"https://{JIRA_SITE}",
        "headers": {
            "Authorization": f"Basic {auth_bytes}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    }


def _make_request(method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
    """Make an authenticated request to Jira API via Atlassian Cloud."""
    try:
        config = _get_jira_config()
        url = f"{config['base_url']}/rest/api/3{endpoint}"

        print(f"[Jira] {method} {url}")

        if method == "GET":
            response = requests.get(url, headers=config["headers"], params=params, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=config["headers"], json=data, timeout=30)
        elif method == "PUT":
            response = requests.put(url, headers=config["headers"], json=data, timeout=30)
        else:
            return {"error": f"Unsupported method: {method}"}

        print(f"[Jira] Response status: {response.status_code}")

        if response.status_code >= 400:
            return {"error": f"Jira API error {response.status_code}", "details": response.text[:500]}

        return response.json() if response.text else {"success": True}

    except ValueError as e:
        return {"error": str(e)}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


# ============================================================================
# Search & Query
# ============================================================================


def search_issues(jql: str, max_results: int = 20, fields: list = None) -> dict:
    """Search Jira issues using JQL (Jira Query Language).

    Args:
        jql: JQL query string (e.g., 'labels = CVE AND status != Done')
        max_results: Maximum number of results to return
        fields: List of fields to return (default: key, summary, status, assignee, labels, priority, created)

    Returns:
        dict with 'issues' list and metadata
    """
    if fields is None:
        fields = ["key", "summary", "status", "assignee", "labels", "priority", "created", "updated", "issuetype"]

    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": ",".join(fields),
    }

    # Use new /search/jql endpoint (old /search was deprecated)
    result = _make_request("GET", "/search/jql", params=params)

    if "error" in result:
        return result

    # Format the issues for easier consumption
    issues = []
    for issue in result.get("issues", []):
        fields_data = issue.get("fields", {})

        # Extract assignee name
        assignee = fields_data.get("assignee")
        assignee_name = assignee.get("displayName") if assignee else "Unassigned"

        # Extract status
        status = fields_data.get("status", {})
        status_name = status.get("name", "Unknown")

        # Extract priority
        priority = fields_data.get("priority", {})
        priority_name = priority.get("name", "None")

        # Extract issue type
        issue_type = fields_data.get("issuetype", {})
        issue_type_name = issue_type.get("name", "Unknown")

        issues.append(
            {
                "key": issue.get("key"),
                "summary": fields_data.get("summary", ""),
                "status": status_name,
                "assignee": assignee_name,
                "labels": fields_data.get("labels", []),
                "priority": priority_name,
                "type": issue_type_name,
                "created": fields_data.get("created", "")[:10],  # Just date part
                "updated": fields_data.get("updated", "")[:10],
            }
        )

    return {
        "total": result.get("total", 0),
        "returned": len(issues),
        "jql": jql,
        "issues": issues,
    }


def get_issue(issue_key: str) -> dict:
    """Get detailed information about a specific Jira issue.

    Args:
        issue_key: The issue key (e.g., 'DEVOPS-123', 'SEC-456')

    Returns:
        dict with issue details including description and comments
    """
    result = _make_request("GET", f"/issue/{issue_key}")

    if "error" in result:
        return result

    fields = result.get("fields", {})

    # Extract description (it's in Atlassian Document Format)
    description = fields.get("description")
    description_text = ""
    if description and isinstance(description, dict):
        # Extract text from ADF format
        description_text = _extract_text_from_adf(description)
    elif isinstance(description, str):
        description_text = description

    # Extract assignee
    assignee = fields.get("assignee")
    assignee_name = assignee.get("displayName") if assignee else "Unassigned"

    # Extract reporter
    reporter = fields.get("reporter")
    reporter_name = reporter.get("displayName") if reporter else "Unknown"

    # Extract status
    status = fields.get("status", {})

    # Extract priority
    priority = fields.get("priority", {})

    # Extract issue type
    issue_type = fields.get("issuetype", {})

    # Extract project
    project = fields.get("project", {})

    return {
        "key": result.get("key"),
        "summary": fields.get("summary", ""),
        "description": description_text[:2000],  # Truncate long descriptions
        "status": status.get("name", "Unknown"),
        "assignee": assignee_name,
        "reporter": reporter_name,
        "labels": fields.get("labels", []),
        "priority": priority.get("name", "None"),
        "type": issue_type.get("name", "Unknown"),
        "project": project.get("name", "Unknown"),
        "project_key": project.get("key", ""),
        "created": fields.get("created", "")[:10],
        "updated": fields.get("updated", "")[:10],
        "url": f"https://{JIRA_SITE}/browse/{result.get('key')}",
    }


def get_issue_comments(issue_key: str, max_results: int = 10) -> dict:
    """Get comments on a Jira issue.

    Args:
        issue_key: The issue key (e.g., 'DEVOPS-123')
        max_results: Maximum number of comments to return

    Returns:
        dict with comments list
    """
    params = {"maxResults": max_results, "orderBy": "-created"}  # Most recent first
    result = _make_request("GET", f"/issue/{issue_key}/comment", params=params)

    if "error" in result:
        return result

    comments = []
    for comment in result.get("comments", []):
        author = comment.get("author", {})
        body = comment.get("body")
        body_text = ""
        if body and isinstance(body, dict):
            body_text = _extract_text_from_adf(body)
        elif isinstance(body, str):
            body_text = body

        comments.append(
            {
                "author": author.get("displayName", "Unknown"),
                "created": comment.get("created", "")[:16].replace("T", " "),
                "body": body_text[:500],  # Truncate long comments
            }
        )

    return {
        "issue_key": issue_key,
        "total": result.get("total", 0),
        "comments": comments,
    }


# ============================================================================
# Label-based queries (common use cases)
# ============================================================================


def get_issues_by_label(label: str, status: str = None, max_results: int = 20) -> dict:
    """Get issues with a specific label.

    Args:
        label: Label to search for (e.g., 'CVE', 'security', 'urgent')
        status: Optional status filter (e.g., 'Open', 'In Progress', 'Done')
        max_results: Maximum number of results

    Returns:
        dict with matching issues
    """
    jql = f'labels = "{label}"'
    if status:
        jql += f' AND status = "{status}"'
    jql += " ORDER BY created DESC"

    return search_issues(jql, max_results)


def get_open_cve_issues(max_results: int = 50) -> dict:
    """Get open CVE/security vulnerability issues.

    Returns issues labeled with CVE that are not Done/Closed.
    """
    jql = "labels in (CVE, cve, security, vulnerability) AND status not in (Done, Closed, Resolved) ORDER BY priority DESC, created DESC"
    return search_issues(jql, max_results)


def get_issues_assigned_to(assignee: str, status: str = None, max_results: int = 20) -> dict:
    """Get issues assigned to a specific person.

    Args:
        assignee: Assignee name or 'currentUser()' for the authenticated user
        status: Optional status filter
        max_results: Maximum number of results
    """
    if assignee.lower() == "me":
        assignee = "currentUser()"

    jql = f"assignee = {assignee}"
    if status:
        jql += f' AND status = "{status}"'
    jql += " ORDER BY updated DESC"

    return search_issues(jql, max_results)


def get_recent_issues(project: str = None, days: int = 7, max_results: int = 20) -> dict:
    """Get recently created issues.

    Args:
        project: Optional project key to filter by
        days: Number of days back to search
        max_results: Maximum number of results
    """
    jql = f"created >= -{days}d"
    if project:
        jql += f' AND project = "{project}"'
    jql += " ORDER BY created DESC"

    return search_issues(jql, max_results)


# ============================================================================
# Issue Management
# ============================================================================


def add_comment(issue_key: str, comment_text: str) -> dict:
    """Add a comment to an issue.

    Args:
        issue_key: The issue key (e.g., 'DEVOPS-123')
        comment_text: The comment text to add

    Returns:
        dict with success status
    """
    # Convert plain text to Atlassian Document Format
    data = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment_text}],
                }
            ],
        }
    }

    result = _make_request("POST", f"/issue/{issue_key}/comment", data=data)

    if "error" in result:
        return result

    return {
        "success": True,
        "issue_key": issue_key,
        "message": f"Comment added to {issue_key}",
    }


def update_issue_status(issue_key: str, transition_name: str) -> dict:
    """Transition an issue to a new status.

    Args:
        issue_key: The issue key
        transition_name: The name of the transition (e.g., 'In Progress', 'Done')

    Returns:
        dict with success status
    """
    # First, get available transitions
    transitions_result = _make_request("GET", f"/issue/{issue_key}/transitions")

    if "error" in transitions_result:
        return transitions_result

    # Find the matching transition
    transitions = transitions_result.get("transitions", [])
    transition_id = None
    available = []

    for t in transitions:
        available.append(t.get("name"))
        if t.get("name", "").lower() == transition_name.lower():
            transition_id = t.get("id")
            break

    if not transition_id:
        return {
            "error": f"Transition '{transition_name}' not found",
            "available_transitions": available,
        }

    # Perform the transition
    data = {"transition": {"id": transition_id}}
    result = _make_request("POST", f"/issue/{issue_key}/transitions", data=data)

    if "error" in result:
        return result

    return {
        "success": True,
        "issue_key": issue_key,
        "message": f"Issue {issue_key} transitioned to '{transition_name}'",
    }


def add_label(issue_key: str, label: str) -> dict:
    """Add a label to an issue.

    Args:
        issue_key: The issue key
        label: The label to add

    Returns:
        dict with success status
    """
    data = {"update": {"labels": [{"add": label}]}}
    result = _make_request("PUT", f"/issue/{issue_key}", data=data)

    if "error" in result:
        return result

    return {
        "success": True,
        "issue_key": issue_key,
        "message": f"Label '{label}' added to {issue_key}",
    }


# ============================================================================
# Helpers
# ============================================================================


def _extract_text_from_adf(adf: dict) -> str:
    """Extract plain text from Atlassian Document Format.

    ADF is a complex nested format - this extracts just the text content.
    """
    if not isinstance(adf, dict):
        return str(adf) if adf else ""

    text_parts = []

    def extract_recursive(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                text_parts.append(node.get("text", ""))
            for child in node.get("content", []):
                extract_recursive(child)
        elif isinstance(node, list):
            for item in node:
                extract_recursive(item)

    extract_recursive(adf)
    return " ".join(text_parts)


# ============================================================================
# High-level handlers for Clippy/MCP
# ============================================================================


def handle_search_jira(query: str, max_results: int = 20) -> dict:
    """Handle natural language Jira search queries.

    Converts common patterns to JQL:
    - "CVE tickets" -> labels = CVE
    - "open bugs" -> type = Bug AND status != Done
    - "my tickets" -> assignee = currentUser()
    - "PROJ-123" -> direct issue lookup

    Args:
        query: Natural language or JQL query
        max_results: Maximum results to return
    """
    query_lower = query.lower().strip()

    # Direct issue key lookup (e.g., "DEVOPS-123")
    if "-" in query and query.replace("-", "").replace(" ", "").isalnum():
        parts = query.upper().split()
        for part in parts:
            if "-" in part and part.split("-")[0].isalpha() and part.split("-")[1].isdigit():
                return get_issue(part)

    # Build JQL from natural language
    jql_parts = []
    order_by = "ORDER BY updated DESC"

    # Label detection
    label_keywords = {
        "cve": "CVE",
        "security": "security",
        "vulnerability": "vulnerability",
        "urgent": "urgent",
        "critical": "critical",
        "bug": None,  # This is a type, not label
    }

    for keyword, label in label_keywords.items():
        if keyword in query_lower and label:
            jql_parts.append(f'labels = "{label}"')

    # Type detection
    if "bug" in query_lower:
        jql_parts.append("type = Bug")
    elif "task" in query_lower:
        jql_parts.append("type = Task")
    elif "story" in query_lower or "stories" in query_lower:
        jql_parts.append("type = Story")
    elif "epic" in query_lower:
        jql_parts.append("type = Epic")

    # Status detection
    if "open" in query_lower or "unresolved" in query_lower:
        jql_parts.append("status not in (Done, Closed, Resolved)")
    elif "done" in query_lower or "closed" in query_lower or "resolved" in query_lower:
        jql_parts.append("status in (Done, Closed, Resolved)")
    elif "in progress" in query_lower:
        jql_parts.append('status = "In Progress"')

    # Assignee detection
    if "my " in query_lower or "assigned to me" in query_lower:
        jql_parts.append("assignee = currentUser()")
    elif "unassigned" in query_lower:
        jql_parts.append("assignee is EMPTY")

    # Priority detection
    if "critical" in query_lower or "highest" in query_lower:
        jql_parts.append("priority in (Critical, Highest)")
        order_by = "ORDER BY priority DESC, updated DESC"
    elif "high" in query_lower:
        jql_parts.append("priority = High")

    # Time-based detection
    if "today" in query_lower:
        jql_parts.append("created >= startOfDay()")
    elif "this week" in query_lower:
        jql_parts.append("created >= startOfWeek()")
    elif "recent" in query_lower:
        jql_parts.append("created >= -7d")

    # If no patterns matched, treat the query as a text search
    if not jql_parts:
        # Search in summary and description
        search_text = query.replace('"', '\\"')
        jql = f'text ~ "{search_text}" {order_by}'
    else:
        jql = " AND ".join(jql_parts) + " " + order_by

    return search_issues(jql, max_results)
