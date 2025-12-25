"""Confluence API tools for documentation search.

Provides functions to search and retrieve Confluence pages.
Uses Confluence Cloud REST API with Basic Auth (same token as Jira).

API Reference: https://developer.atlassian.com/cloud/confluence/rest/v1/
CQL Reference: https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/
"""

import base64
import os
import re
import sys

import requests

# Add project root to path to import shared utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.lib.utils.secrets import get_secret

# Confluence site configuration (same Atlassian instance as Jira)
CONFLUENCE_SITE = "completemerchantsolutions.atlassian.net"
CONFLUENCE_EMAIL = "gstarkman@nex.io"


def _get_confluence_config() -> dict:
    """Get Confluence configuration for Basic Auth."""
    # Uses same API token as Jira (Atlassian account token)
    api_token = get_secret("JIRA_API_TOKEN")
    if not api_token:
        raise ValueError("Missing JIRA_API_TOKEN in secrets (used for Confluence too)")

    # Basic Auth: base64(email:api_token)
    auth_string = f"{CONFLUENCE_EMAIL}:{api_token}"
    auth_bytes = base64.b64encode(auth_string.encode()).decode()

    return {
        "base_url": f"https://{CONFLUENCE_SITE}/wiki",
        "headers": {
            "Authorization": f"Basic {auth_bytes}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    }


def _make_request(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated GET request to Confluence API."""
    try:
        config = _get_confluence_config()
        url = f"{config['base_url']}/rest/api{endpoint}"

        print(f"[Confluence] GET {url}")

        response = requests.get(url, headers=config["headers"], params=params, timeout=30)

        print(f"[Confluence] Response status: {response.status_code}")

        if response.status_code >= 400:
            return {"error": f"Confluence API error {response.status_code}", "details": response.text[:500]}

        return response.json() if response.text else {"success": True}

    except ValueError as e:
        return {"error": str(e)}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


def _html_to_text(html: str) -> str:
    """Convert HTML content to plain text."""
    if not html:
        return ""

    # Remove script and style elements
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Convert common elements
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"<h[1-6][^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n", text, flags=re.IGNORECASE)

    # Remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    # Clean up whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r" +", " ", text)

    return text.strip()


# ============================================================================
# Search & Query
# ============================================================================


def handle_search(query: str, space_key: str = None, limit: int = 10) -> dict:
    """Search Confluence pages using CQL (Confluence Query Language).

    Args:
        query: Search text (will search title and content)
        space_key: Limit to specific space (e.g., 'DEV', 'HR', 'ENG')
        limit: Maximum results (default 10, max 50)

    Returns:
        dict with 'results' list containing matching pages
    """
    # Build CQL query
    cql_parts = [f'text ~ "{query}"']

    if space_key:
        cql_parts.append(f'space = "{space_key}"')

    cql = " AND ".join(cql_parts)
    cql += " ORDER BY lastmodified DESC"

    params = {
        "cql": cql,
        "limit": min(limit, 50),  # API max is 50
    }

    data = _make_request("/search", params=params)

    if "error" in data:
        return data

    results = []
    for item in data.get("results", []):
        content = item.get("content", {}) or item
        result = {
            "id": content.get("id"),
            "title": content.get("title") or item.get("title"),
            "type": content.get("type", "page"),
            "space": content.get("space", {}).get("key") if content.get("space") else None,
            "url": f"https://{CONFLUENCE_SITE}/wiki" + content.get("_links", {}).get("webui", ""),
            "last_modified": item.get("lastModified"),
            "excerpt": _html_to_text(item.get("excerpt", ""))[:300],
        }
        results.append(result)

    return {
        "query": query,
        "space_filter": space_key,
        "total_results": len(results),
        "results": results,
    }


def handle_get_page(page_id: str, include_body: bool = True) -> dict:
    """Get a specific Confluence page by ID.

    Args:
        page_id: Confluence page ID
        include_body: Whether to include page content (default True)

    Returns:
        dict with page details and content
    """
    expand = ["space", "version", "ancestors"]
    if include_body:
        expand.append("body.storage")

    params = {"expand": ",".join(expand)}

    data = _make_request(f"/content/{page_id}", params=params)

    if "error" in data:
        return data

    body_html = data.get("body", {}).get("storage", {}).get("value", "")

    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "type": data.get("type"),
        "space": data.get("space", {}).get("key"),
        "space_name": data.get("space", {}).get("name"),
        "url": f"https://{CONFLUENCE_SITE}/wiki" + data.get("_links", {}).get("webui", ""),
        "version": data.get("version", {}).get("number"),
        "last_modified": data.get("version", {}).get("when"),
        "last_modified_by": data.get("version", {}).get("by", {}).get("displayName"),
        "ancestors": [{"id": a.get("id"), "title": a.get("title")} for a in data.get("ancestors", [])],
        "content": _html_to_text(body_html) if include_body else None,
    }


def handle_get_page_by_title(title: str, space_key: str) -> dict:
    """Get a Confluence page by its exact title.

    Args:
        title: Exact page title
        space_key: Space key where the page lives

    Returns:
        dict with page details
    """
    params = {
        "title": title,
        "spaceKey": space_key,
        "expand": "space,version,body.storage",
    }

    data = _make_request("/content", params=params)

    if "error" in data:
        return data

    results = data.get("results", [])
    if not results:
        return {"error": f"Page '{title}' not found in space '{space_key}'"}

    page = results[0]
    body_html = page.get("body", {}).get("storage", {}).get("value", "")

    return {
        "id": page.get("id"),
        "title": page.get("title"),
        "space": page.get("space", {}).get("key"),
        "url": f"https://{CONFLUENCE_SITE}/wiki" + page.get("_links", {}).get("webui", ""),
        "version": page.get("version", {}).get("number"),
        "content": _html_to_text(body_html),
    }


def handle_list_spaces(limit: int = 50) -> dict:
    """List all available Confluence spaces.

    Args:
        limit: Maximum spaces to return

    Returns:
        dict with 'spaces' list
    """
    params = {
        "limit": min(limit, 100),
        "expand": "description.plain",
    }

    data = _make_request("/space", params=params)

    if "error" in data:
        return data

    spaces = []
    for space in data.get("results", []):
        spaces.append(
            {
                "key": space.get("key"),
                "name": space.get("name"),
                "type": space.get("type"),
                "description": space.get("description", {}).get("plain", {}).get("value", "")[:200],
                "url": f"https://{CONFLUENCE_SITE}/wiki/spaces/{space.get('key')}",
            }
        )

    return {
        "total_spaces": len(spaces),
        "spaces": spaces,
    }


def handle_get_space_pages(space_key: str, limit: int = 25) -> dict:
    """List pages in a specific Confluence space.

    Args:
        space_key: Space key (e.g., 'DEV', 'HR')
        limit: Maximum pages to return

    Returns:
        dict with 'pages' list
    """
    params = {
        "spaceKey": space_key,
        "type": "page",
        "limit": min(limit, 100),
        "orderby": "title",
        "expand": "version",
    }

    data = _make_request("/content", params=params)

    if "error" in data:
        return data

    pages = []
    for page in data.get("results", []):
        pages.append(
            {
                "id": page.get("id"),
                "title": page.get("title"),
                "url": f"https://{CONFLUENCE_SITE}/wiki" + page.get("_links", {}).get("webui", ""),
                "last_modified": page.get("version", {}).get("when"),
            }
        )

    return {
        "space": space_key,
        "total_pages": len(pages),
        "pages": pages,
    }


def handle_get_recent_updates(space_key: str = None, limit: int = 15) -> dict:
    """Get recently updated pages.

    Args:
        space_key: Limit to specific space (optional)
        limit: Maximum results

    Returns:
        dict with 'pages' list
    """
    # Build CQL query for recent updates
    cql_parts = ["type = page"]
    if space_key:
        cql_parts.append(f'space = "{space_key}"')

    cql = " AND ".join(cql_parts)
    cql += " ORDER BY lastmodified DESC"

    params = {
        "cql": cql,
        "limit": min(limit, 50),
    }

    data = _make_request("/search", params=params)

    if "error" in data:
        return data

    pages = []
    for item in data.get("results", []):
        content = item.get("content", {}) or item
        pages.append(
            {
                "id": content.get("id"),
                "title": content.get("title") or item.get("title"),
                "space": content.get("space", {}).get("key") if content.get("space") else None,
                "url": f"https://{CONFLUENCE_SITE}/wiki" + content.get("_links", {}).get("webui", ""),
                "last_modified": item.get("lastModified"),
                "modified_by": (
                    item.get("lastModifiedBy", {}).get("displayName") if item.get("lastModifiedBy") else None
                ),
            }
        )

    return {
        "space_filter": space_key,
        "total_pages": len(pages),
        "pages": pages,
    }


def handle_search_by_label(label: str, space_key: str = None, limit: int = 20) -> dict:
    """Find pages with a specific label.

    Args:
        label: Label to search for (e.g., 'runbook', 'architecture', 'hr-policy')
        space_key: Limit to specific space (optional)
        limit: Maximum results

    Returns:
        dict with 'pages' list
    """
    cql_parts = [f'label = "{label}"']
    if space_key:
        cql_parts.append(f'space = "{space_key}"')

    cql = " AND ".join(cql_parts)
    cql += " ORDER BY lastmodified DESC"

    params = {
        "cql": cql,
        "limit": min(limit, 50),
    }

    data = _make_request("/search", params=params)

    if "error" in data:
        return data

    pages = []
    for item in data.get("results", []):
        content = item.get("content", {}) or item
        pages.append(
            {
                "id": content.get("id"),
                "title": content.get("title") or item.get("title"),
                "space": content.get("space", {}).get("key") if content.get("space") else None,
                "url": f"https://{CONFLUENCE_SITE}/wiki" + content.get("_links", {}).get("webui", ""),
                "excerpt": _html_to_text(item.get("excerpt", ""))[:200],
            }
        )

    return {
        "label": label,
        "space_filter": space_key,
        "total_pages": len(pages),
        "pages": pages,
    }


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("CONFLUENCE API TEST")
    print("=" * 60)

    # Test 1: List spaces
    print("\n=== Test 1: List Spaces ===")
    result = handle_list_spaces(limit=10)
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Found {result['total_spaces']} spaces:")
        for space in result.get("spaces", [])[:5]:
            print(f"  - {space['key']}: {space['name']}")

    # Test 2: Search
    print("\n=== Test 2: Search ===")
    result = handle_search("onboarding", limit=5)
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Found {result['total_results']} results for 'onboarding':")
        for page in result.get("results", []):
            print(f"  - {page['title']} ({page['space']})")

    # Test 3: Recent updates
    print("\n=== Test 3: Recent Updates ===")
    result = handle_get_recent_updates(limit=5)
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Recent updates:")
        for page in result.get("pages", []):
            print(
                f"  - {page['title']} (modified: {page['last_modified'][:10] if page.get('last_modified') else 'unknown'})"
            )
