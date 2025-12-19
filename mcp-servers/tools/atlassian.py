"""Atlassian Admin v2 API tools for user/group management.

These tools use the Atlassian Admin API v2 for onboarding/offboarding workflows.
API Reference: https://developer.atlassian.com/cloud/admin/organization/rest/
"""

import requests

import sys
import os

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.secrets import get_secret

# Atlassian Admin API base URL
ATLASSIAN_ADMIN_API = "https://api.atlassian.com"


def _get_auth_headers() -> dict:
    """Get authentication headers for Atlassian API."""
    api_token = get_secret("ATLASSIAN_API_TOKEN")
    if not api_token:
        raise ValueError("ATLASSIAN_API_TOKEN not configured in Secrets Manager")

    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get_org_id() -> str:
    """Get Atlassian Organization ID."""
    org_id = get_secret("ATLASSIAN_ORG_ID")
    if not org_id:
        raise ValueError("ATLASSIAN_ORG_ID not configured in Secrets Manager")
    return org_id


def _get_directory_id() -> str:
    """Get Atlassian Directory ID."""
    directory_id = get_secret("ATLASSIAN_DIRECTORY_ID")
    if not directory_id:
        raise ValueError("ATLASSIAN_DIRECTORY_ID not configured in Secrets Manager")
    return directory_id


def _make_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make an authenticated request to Atlassian Admin API."""
    try:
        headers = _get_auth_headers()
        url = f"{ATLASSIAN_ADMIN_API}{endpoint}"

        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            return {"error": f"Unsupported method: {method}"}

        if response.status_code == 204:
            return {"success": True, "message": "Operation completed successfully"}

        if response.status_code >= 400:
            return {"error": f"API error {response.status_code}", "details": response.text}

        return response.json() if response.text else {"success": True}

    except ValueError as e:
        return {"error": str(e)}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


# ============================================================================
# Directory Tools
# ============================================================================

def handle_get_directories() -> dict:
    """Get directories in the organization."""
    org_id = _get_org_id()
    endpoint = f"/v2/orgs/{org_id}/directories"
    return _make_request("GET", endpoint)


# ============================================================================
# User Tools
# ============================================================================

def handle_list_users(limit: int = 100, cursor: str = None) -> dict:
    """List users in the organization directory."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/users?limit={limit}"
    if cursor:
        endpoint += f"&cursor={cursor}"

    result = _make_request("GET", endpoint)

    if "data" in result:
        users = []
        for user in result.get("data", []):
            users.append({
                "account_id": user.get("accountId"),
                "name": user.get("name"),
                "email": user.get("email"),
                "status": user.get("accountStatus"),
                "last_active": user.get("lastActive"),
            })
        result["formatted_users"] = users
        result["count"] = len(users)

    return result


def handle_suspend_user(account_id: str) -> dict:
    """Suspend a user's access in the directory."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/users/{account_id}/suspend"
    result = _make_request("POST", endpoint)

    if "error" not in result:
        result["message"] = f"User {account_id} suspended successfully"
        result["action"] = "suspend"

    return result


def handle_restore_user(account_id: str) -> dict:
    """Restore a suspended user's access."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/users/{account_id}/restore"
    result = _make_request("POST", endpoint)

    if "error" not in result:
        result["message"] = f"User {account_id} restored successfully"
        result["action"] = "restore"

    return result


def handle_remove_user(account_id: str) -> dict:
    """Remove a user from the directory completely."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/users/{account_id}"
    result = _make_request("DELETE", endpoint)

    if "error" not in result:
        result["message"] = f"User {account_id} removed from directory"
        result["action"] = "remove"

    return result


# ============================================================================
# Group Tools
# ============================================================================

def handle_list_groups(limit: int = 100) -> dict:
    """List all groups in the organization directory."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups?limit={limit}"
    result = _make_request("GET", endpoint)

    if "data" in result:
        groups = []
        for group in result.get("data", []):
            groups.append({
                "group_id": group.get("id"),
                "name": group.get("name"),
                "description": group.get("description", ""),
                "member_count": group.get("memberCount", 0),
            })
        result["formatted_groups"] = groups
        result["count"] = len(groups)

    return result


def handle_create_group(name: str, description: str = "") -> dict:
    """Create a new group in the directory."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups"
    data = {"name": name}
    if description:
        data["description"] = description

    result = _make_request("POST", endpoint, data)

    if "error" not in result:
        result["message"] = f"Group '{name}' created successfully"

    return result


def handle_delete_group(group_id: str) -> dict:
    """Delete a group from the directory."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups/{group_id}"
    result = _make_request("DELETE", endpoint)

    if "error" not in result:
        result["message"] = f"Group {group_id} deleted"

    return result


def handle_add_user_to_group(group_id: str, account_id: str) -> dict:
    """Add a user to a group."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups/{group_id}/memberships"
    data = {"accountId": account_id}
    result = _make_request("POST", endpoint, data)

    if "error" not in result:
        result["message"] = f"User {account_id} added to group {group_id}"

    return result


def handle_remove_user_from_group(group_id: str, account_id: str) -> dict:
    """Remove a user from a group."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups/{group_id}/memberships/{account_id}"
    result = _make_request("DELETE", endpoint)

    if "error" not in result:
        result["message"] = f"User {account_id} removed from group {group_id}"

    return result


# ============================================================================
# Role/Access Tools
# ============================================================================

def handle_grant_group_access(group_id: str, role: str, resource_id: str = None) -> dict:
    """Grant product access to a group via role assignment."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups/{group_id}/role-assignments/assign"
    data = {"role": role}
    if resource_id:
        data["resourceId"] = resource_id

    result = _make_request("POST", endpoint, data)

    if "error" not in result:
        result["message"] = f"Role '{role}' granted to group {group_id}"

    return result


def handle_revoke_group_access(group_id: str, role: str, resource_id: str = None) -> dict:
    """Revoke product access from a group."""
    org_id = _get_org_id()
    directory_id = _get_directory_id()

    endpoint = f"/v2/orgs/{org_id}/directories/{directory_id}/groups/{group_id}/role-assignments/revoke"
    data = {"role": role}
    if resource_id:
        data["resourceId"] = resource_id

    result = _make_request("POST", endpoint, data)

    if "error" not in result:
        result["message"] = f"Role '{role}' revoked from group {group_id}"

    return result
