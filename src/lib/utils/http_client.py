"""Shared HTTP client utilities for API requests.

Provides a consistent pattern for making authenticated API requests
across all external services (Bitbucket, Jira, PagerDuty, Coralogix, etc.)
"""

import time

import requests


class APIClient:
    """Base class for authenticated API clients.

    Usage:
        class BitbucketClient(APIClient):
            def __init__(self):
                super().__init__(
                    base_url="https://api.bitbucket.org/2.0",
                    service_name="Bitbucket",
                    timeout=10
                )

            def _get_auth(self):
                return {"headers": {"Authorization": f"Bearer {token}"}}
    """

    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: int = 10,
        default_headers: dict = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = timeout
        self.default_headers = default_headers or {}

    def _get_auth(self) -> dict:
        """Override to provide authentication.

        Returns dict that can be unpacked into requests.get/post:
        - {"headers": {"Authorization": "Bearer xxx"}} for Bearer auth
        - {"auth": ("user", "pass")} for Basic auth
        - {"headers": {"X-Api-Key": "xxx"}} for API key auth
        """
        return {}

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint."""
        endpoint = endpoint.lstrip("/")
        return f"{self.base_url}/{endpoint}"

    def _log(self, message: str):
        """Log a message with service prefix."""
        print(f"[{self.service_name}] {message}")

    def get(
        self,
        endpoint: str,
        params: dict = None,
        timeout: int = None,
        raw_response: bool = False,
    ) -> dict:
        """Make GET request to API endpoint.

        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
            timeout: Override default timeout
            raw_response: Return raw text instead of JSON

        Returns:
            dict with response data or {"error": "message"}
        """
        return self._request("GET", endpoint, params=params, timeout=timeout, raw_response=raw_response)

    def post(
        self,
        endpoint: str,
        data: dict = None,
        json_data: dict = None,
        timeout: int = None,
    ) -> dict:
        """Make POST request to API endpoint.

        Args:
            endpoint: API endpoint (without base URL)
            data: Form data
            json_data: JSON body
            timeout: Override default timeout

        Returns:
            dict with response data or {"error": "message"}
        """
        return self._request("POST", endpoint, data=data, json_data=json_data, timeout=timeout)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        data: dict = None,
        json_data: dict = None,
        timeout: int = None,
        raw_response: bool = False,
    ) -> dict:
        """Make HTTP request with consistent error handling."""
        url = self._build_url(endpoint)
        timeout = timeout or self.timeout

        # Get auth kwargs
        auth_kwargs = self._get_auth()

        # Merge headers
        headers = {**self.default_headers}
        if "headers" in auth_kwargs:
            headers.update(auth_kwargs.pop("headers"))

        self._log(f"{method} {endpoint}")
        start = time.time()

        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_data,
                headers=headers if headers else None,
                timeout=timeout,
                **auth_kwargs,
            )

            elapsed = time.time() - start
            self._log(f"Response: {response.status_code} in {elapsed:.1f}s")

            # Handle common error codes
            if response.status_code == 401:
                return {
                    "error": f"{self.service_name} API returned 401 Unauthorized",
                    "auth_failed": True,
                    "action_required": f"Check {self.service_name} credentials in Secrets Manager",
                }
            elif response.status_code == 403:
                return {
                    "error": f"{self.service_name} API returned 403 Forbidden",
                    "access_denied": True,
                }
            elif response.status_code == 404:
                return {"error": f"Not found: {endpoint}"}
            elif response.status_code >= 400:
                return {"error": f"{self.service_name} API error: {response.status_code}"}

            # Return response
            if raw_response:
                return {"text": response.text, "status_code": response.status_code}

            # Try to parse JSON
            try:
                return response.json()
            except ValueError:
                # Non-JSON response
                return {"text": response.text, "status_code": response.status_code}

        except requests.exceptions.Timeout:
            self._log(f"Timeout after {timeout}s for {endpoint}")
            return {"error": f"{self.service_name} API timeout for {endpoint}"}
        except requests.exceptions.ConnectionError as e:
            self._log(f"Connection error: {e}")
            return {"error": f"{self.service_name} API connection error"}
        except Exception as e:
            self._log(f"Request error: {e}")
            return {"error": str(e)}


def make_request(
    url: str,
    method: str = "GET",
    headers: dict = None,
    params: dict = None,
    json_data: dict = None,
    auth: tuple = None,
    timeout: int = 10,
    service_name: str = "API",
) -> dict:
    """Simple function for one-off API requests.

    For repeated calls to the same API, use APIClient subclass instead.

    Args:
        url: Full URL to request
        method: HTTP method
        headers: Request headers
        params: Query parameters
        json_data: JSON body for POST/PUT
        auth: Basic auth tuple (username, password)
        timeout: Request timeout in seconds
        service_name: Service name for logging

    Returns:
        dict with response data or {"error": "message"}
    """
    print(f"[{service_name}] {method} {url}")
    start = time.time()

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            auth=auth,
            timeout=timeout,
        )

        elapsed = time.time() - start
        print(f"[{service_name}] Response: {response.status_code} in {elapsed:.1f}s")

        if response.status_code >= 400:
            return {"error": f"{service_name} API error: {response.status_code}"}

        try:
            return response.json()
        except ValueError:
            return {"text": response.text, "status_code": response.status_code}

    except requests.exceptions.Timeout:
        return {"error": f"{service_name} API timeout"}
    except Exception as e:
        return {"error": str(e)}
