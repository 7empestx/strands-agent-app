"""PagerDuty API tools for incident management.

Provides functions to list and get details about PagerDuty incidents.
Uses PagerDuty REST API v2 with API token authentication.

API Reference: https://developer.pagerduty.com/api-reference/
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.lib.utils.secrets import get_secret


def _get_pagerduty_config() -> dict:
    """Get PagerDuty configuration with API token."""
    api_token = get_secret("PAGERDUTY_API_TOKEN")
    if not api_token:
        raise ValueError("Missing PAGERDUTY_API_TOKEN in secrets")

    return {
        "base_url": "https://api.pagerduty.com",
        "headers": {
            "Authorization": f"Token token={api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    }


def _make_request(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated request to PagerDuty API."""
    try:
        config = _get_pagerduty_config()
        url = f"{config['base_url']}{endpoint}"

        print(f"[PagerDuty] GET {endpoint}")

        response = requests.get(url, headers=config["headers"], params=params, timeout=30)

        print(f"[PagerDuty] Response status: {response.status_code}")

        if response.status_code >= 400:
            return {"error": f"PagerDuty API error {response.status_code}", "details": response.text[:500]}

        return response.json() if response.text else {"success": True}

    except ValueError as e:
        return {"error": str(e)}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


# ============================================================================
# Incident Functions
# ============================================================================


def list_incidents(
    statuses: list = None,
    since: str = None,
    until: str = None,
    urgencies: list = None,
    limit: int = 25,
) -> dict:
    """List PagerDuty incidents.

    Args:
        statuses: Filter by status - 'triggered', 'acknowledged', 'resolved'
                  Default: ['triggered', 'acknowledged'] (active incidents)
        since: Start of date range (ISO8601 or relative like '-7d')
        until: End of date range (ISO8601)
        urgencies: Filter by urgency - 'high', 'low'
        limit: Max results (default: 25, max: 100)

    Returns:
        dict with incidents list and metadata
    """
    params = {"limit": min(limit, 100)}

    # Default to active incidents if no status specified
    if statuses is None:
        statuses = ["triggered", "acknowledged"]

    # Add statuses as repeated params
    for status in statuses:
        params.setdefault("statuses[]", []).append(status) if isinstance(params.get("statuses[]"), list) else None

    # Build params properly for requests
    param_list = []
    for status in statuses:
        param_list.append(("statuses[]", status))
    if urgencies:
        for urgency in urgencies:
            param_list.append(("urgencies[]", urgency))

    # Handle relative date strings
    if since:
        if since.startswith("-") and since.endswith("d"):
            days = int(since[1:-1])
            since_dt = datetime.now(timezone.utc) - timedelta(days=days)
            since = since_dt.isoformat()
        param_list.append(("since", since))

    if until:
        param_list.append(("until", until))

    param_list.append(("limit", str(limit)))

    # Make request with list of tuples for repeated params
    try:
        config = _get_pagerduty_config()
        url = f"{config['base_url']}/incidents"

        print(f"[PagerDuty] GET /incidents with {len(statuses)} statuses")

        response = requests.get(url, headers=config["headers"], params=param_list, timeout=30)

        print(f"[PagerDuty] Response status: {response.status_code}")

        if response.status_code >= 400:
            return {"error": f"PagerDuty API error {response.status_code}", "details": response.text[:500]}

        result = response.json()

    except ValueError as e:
        return {"error": str(e)}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

    # Format incidents for easier consumption
    incidents = []
    for incident in result.get("incidents", []):
        service = incident.get("service", {})
        assignees = incident.get("assignments", [])
        assignee_names = [a.get("assignee", {}).get("summary", "Unknown") for a in assignees]

        incidents.append(
            {
                "id": incident.get("id"),
                "incident_number": incident.get("incident_number"),
                "title": incident.get("title", ""),
                "status": incident.get("status"),
                "urgency": incident.get("urgency"),
                "service": service.get("summary", "Unknown"),
                "service_id": service.get("id"),
                "created_at": incident.get("created_at", "")[:16].replace("T", " "),
                "assignees": assignee_names if assignee_names else ["Unassigned"],
                "html_url": incident.get("html_url", ""),
            }
        )

    return {
        "total": len(incidents),
        "statuses": statuses,
        "incidents": incidents,
    }


def get_incident(incident_id: str) -> dict:
    """Get detailed information about a specific incident.

    Args:
        incident_id: The incident ID (e.g., 'PXXXXXX') or incident number

    Returns:
        dict with incident details
    """
    # Handle incident number vs ID
    endpoint = f"/incidents/{incident_id}"

    result = _make_request(endpoint)

    if "error" in result:
        return result

    incident = result.get("incident", {})
    service = incident.get("service", {})
    assignees = incident.get("assignments", [])
    assignee_names = [a.get("assignee", {}).get("summary", "Unknown") for a in assignees]

    # Get first trigger log entry for more context
    first_trigger = incident.get("first_trigger_log_entry", {})
    trigger_summary = first_trigger.get("channel", {}).get("summary", "")

    return {
        "id": incident.get("id"),
        "incident_number": incident.get("incident_number"),
        "title": incident.get("title", ""),
        "description": incident.get("description", ""),
        "status": incident.get("status"),
        "urgency": incident.get("urgency"),
        "priority": incident.get("priority", {}).get("summary") if incident.get("priority") else None,
        "service": service.get("summary", "Unknown"),
        "service_id": service.get("id"),
        "created_at": incident.get("created_at", "")[:16].replace("T", " "),
        "updated_at": incident.get("updated_at", "")[:16].replace("T", " "),
        "assignees": assignee_names if assignee_names else ["Unassigned"],
        "trigger_summary": trigger_summary,
        "html_url": incident.get("html_url", ""),
        "escalation_policy": incident.get("escalation_policy", {}).get("summary"),
    }


def get_incident_log(incident_id: str, limit: int = 10) -> dict:
    """Get log entries (timeline) for an incident.

    Args:
        incident_id: The incident ID
        limit: Max log entries to return

    Returns:
        dict with log entries
    """
    endpoint = f"/incidents/{incident_id}/log_entries"
    params = {"limit": limit}

    result = _make_request(endpoint, params)

    if "error" in result:
        return result

    log_entries = []
    for entry in result.get("log_entries", []):
        agent = entry.get("agent", {})

        log_entries.append(
            {
                "type": entry.get("type", "").replace("_log_entry", ""),
                "created_at": entry.get("created_at", "")[:16].replace("T", " "),
                "summary": entry.get("channel", {}).get("summary", entry.get("summary", "")),
                "agent": agent.get("summary", "System") if agent else "System",
            }
        )

    return {
        "incident_id": incident_id,
        "total": len(log_entries),
        "log_entries": log_entries,
    }


def get_incident_notes(incident_id: str) -> dict:
    """Get notes added to an incident.

    Args:
        incident_id: The incident ID

    Returns:
        dict with notes
    """
    endpoint = f"/incidents/{incident_id}/notes"

    result = _make_request(endpoint)

    if "error" in result:
        return result

    notes = []
    for note in result.get("notes", []):
        user = note.get("user", {})

        notes.append(
            {
                "content": note.get("content", ""),
                "created_at": note.get("created_at", "")[:16].replace("T", " "),
                "user": user.get("summary", "Unknown"),
            }
        )

    return {
        "incident_id": incident_id,
        "total": len(notes),
        "notes": notes,
    }


# ============================================================================
# Service Functions
# ============================================================================


def list_services(limit: int = 50) -> dict:
    """List PagerDuty services.

    Args:
        limit: Max results

    Returns:
        dict with services list
    """
    params = {"limit": min(limit, 100)}

    result = _make_request("/services", params)

    if "error" in result:
        return result

    services = []
    for service in result.get("services", []):
        services.append(
            {
                "id": service.get("id"),
                "name": service.get("name"),
                "description": service.get("description", ""),
                "status": service.get("status"),
                "created_at": service.get("created_at", "")[:10],
            }
        )

    return {
        "total": len(services),
        "services": services,
    }


# ============================================================================
# High-level handlers for Clippy
# ============================================================================


def handle_active_incidents() -> dict:
    """Get currently active (triggered/acknowledged) incidents.

    Returns incidents that need attention right now.
    """
    return list_incidents(statuses=["triggered", "acknowledged"], limit=25)


def handle_recent_incidents(days: int = 7) -> dict:
    """Get incidents from the past N days (all statuses).

    Args:
        days: Number of days to look back (default: 7)
    """
    since = f"-{days}d"
    return list_incidents(
        statuses=["triggered", "acknowledged", "resolved"],
        since=since,
        limit=50,
    )


def handle_incident_details(incident_id: str) -> dict:
    """Get full details about an incident including notes and log.

    Args:
        incident_id: Incident ID or number

    Returns:
        Combined incident details, notes, and timeline
    """
    # Get main incident details
    incident = get_incident(incident_id)
    if "error" in incident:
        return incident

    # Get notes
    notes = get_incident_notes(incident_id)
    if "error" not in notes:
        incident["notes"] = notes.get("notes", [])

    # Get recent log entries
    log = get_incident_log(incident_id, limit=5)
    if "error" not in log:
        incident["recent_activity"] = log.get("log_entries", [])

    return incident


def extract_service_name_from_incident(incident: dict) -> str:
    """Extract a likely service/repo name from incident details.

    Tries to map PagerDuty service names to actual repo names
    for cross-referencing with Coralogix and code search.
    """
    service = incident.get("service", "")
    title = incident.get("title", "")
    service_lower = service.lower()
    title_lower = title.lower()

    # More specific patterns first (order matters)
    service_patterns = [
        ("emvio-dashboard-app", "emvio-dashboard-app"),
        ("emvio-retail-iframe", "emvio-retail-iframe-app"),
        ("emvio-gateway", "emvio-gateway"),
        ("emvio-underwriting", "emvio-underwriting-service"),
        ("cast-core", "cast-core"),
        ("cast-app", "cast-app"),
        ("cforce-service", "cforce-service"),
        ("cforce", "cforce-service"),
        ("mrrobot-auth", "mrrobot-auth-rest"),
    ]

    # Check service name with specific patterns
    for pattern, repo in service_patterns:
        if pattern in service_lower:
            return repo

    # Check title with specific patterns
    for pattern, repo in service_patterns:
        if pattern in title_lower:
            return repo

    # Strip common suffixes to get base service name
    # e.g., "emvio-dashboard-app-staging" -> "emvio-dashboard-app"
    base_service = service_lower
    for suffix in ["-prod", "-production", "-staging", "-dev", "-development", "-sandbox", "-devopslocal"]:
        if base_service.endswith(suffix):
            base_service = base_service[: -len(suffix)]
            break

    # Return cleaned up service name
    return base_service if base_service else service
