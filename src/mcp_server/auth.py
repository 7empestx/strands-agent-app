"""Azure AD OAuth2/OIDC authentication for Clippy Dashboard.

Provides SSO authentication for all MrRobot employees using Azure AD (Entra ID).
Uses MSAL (Microsoft Authentication Library) for token handling.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import jwt
import msal
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.lib.utils.secrets import get_secret

# Configuration - redirect URIs per environment
REDIRECT_URIS = {
    "dev": "https://ai-agent.mrrobot.dev/auth/callback",
    "prod": "https://ai-agent.nex.io/auth/callback",
    "local": "http://localhost:3000/auth/callback",
}
COOKIE_NAME = "clippy_session"
COOKIE_MAX_AGE = 8 * 60 * 60  # 8 hours
SESSION_SECRET_KEY = None  # Lazily loaded

# Azure AD endpoints
AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"
# MSAL scopes - use User.Read for basic profile (openid/profile are added automatically)
SCOPES = ["User.Read"]

# DynamoDB session store for OAuth state (handles multi-instance ECS deployments)
_dynamodb_client = None


def _get_dynamodb_client():
    """Get or create DynamoDB client."""
    global _dynamodb_client
    if _dynamodb_client is None:
        import boto3

        _dynamodb_client = boto3.client("dynamodb", region_name="us-east-1")
    return _dynamodb_client


def _get_oauth_state_table() -> str:
    """Get the DynamoDB table name for OAuth state."""
    env = os.environ.get("ENVIRONMENT", "dev")
    return f"mrrobot-ai-feedback-{env}"


def _store_oauth_state(state_hash: str, data: dict) -> None:
    """Store OAuth state in DynamoDB with 5 minute TTL."""
    import time

    client = _get_dynamodb_client()
    ttl = int(time.time()) + 300  # 5 minutes
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        client.put_item(
            TableName=_get_oauth_state_table(),
            Item={
                "id": {"S": f"OAUTH_STATE#{state_hash}"},
                "timestamp": {"S": timestamp},
                "data": {"S": json.dumps(data)},
                "ttl": {"N": str(ttl)},
            },
        )
    except Exception as e:
        print(f"[Auth] Failed to store OAuth state: {e}")


def _get_oauth_state(state_hash: str) -> dict | None:
    """Retrieve and delete OAuth state from DynamoDB (one-time use)."""
    client = _get_dynamodb_client()
    try:
        # Query for items with this state hash (we don't know the exact timestamp)
        response = client.query(
            TableName=_get_oauth_state_table(),
            KeyConditionExpression="id = :id",
            ExpressionAttributeValues={
                ":id": {"S": f"OAUTH_STATE#{state_hash}"},
            },
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None

        item = items[0]
        timestamp = item["timestamp"]["S"]

        # Delete it (one-time use)
        client.delete_item(
            TableName=_get_oauth_state_table(),
            Key={
                "id": {"S": f"OAUTH_STATE#{state_hash}"},
                "timestamp": {"S": timestamp},
            },
        )

        return json.loads(item["data"]["S"])
    except Exception as e:
        print(f"[Auth] Failed to get OAuth state: {e}")
        return None


def _get_config() -> dict:
    """Get Azure AD configuration from secrets."""
    client_id = get_secret("AZURE_AD_CLIENT_ID")
    client_secret = get_secret("AZURE_AD_CLIENT_SECRET")
    tenant_id = get_secret("AZURE_AD_TENANT_ID")

    if not all([client_id, client_secret, tenant_id]):
        return None

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "tenant_id": tenant_id,
        "authority": AUTHORITY_TEMPLATE.format(tenant_id=tenant_id),
    }


def _get_msal_app() -> Optional[msal.ConfidentialClientApplication]:
    """Create MSAL confidential client application."""
    config = _get_config()
    if not config:
        return None

    return msal.ConfidentialClientApplication(
        config["client_id"],
        authority=config["authority"],
        client_credential=config["client_secret"],
    )


def _get_session_secret() -> str:
    """Get or generate session signing secret."""
    global SESSION_SECRET_KEY
    if SESSION_SECRET_KEY is None:
        # Try to get from secrets, fall back to generated key
        SESSION_SECRET_KEY = get_secret("SESSION_SECRET_KEY") or secrets.token_hex(32)
    return SESSION_SECRET_KEY


def _create_session_token(user_info: dict) -> str:
    """Create a signed session token."""
    payload = {
        "sub": user_info.get("oid", user_info.get("sub")),  # Azure AD object ID
        "email": user_info.get("preferred_username", user_info.get("email")),
        "name": user_info.get("name", ""),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=COOKIE_MAX_AGE),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_session_secret(), algorithm="HS256")


def _verify_session_token(token: str) -> Optional[dict]:
    """Verify and decode a session token."""
    try:
        payload = jwt.decode(token, _get_session_secret(), algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        print("[Auth] Session token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[Auth] Invalid session token: {e}")
        return None


def get_redirect_uri() -> str:
    """Get the appropriate redirect URI based on environment."""
    # Check if running locally
    if os.environ.get("LOCAL_DEV") or os.environ.get("VITE_API_URL"):
        return REDIRECT_URIS["local"]
    # Check for prod environment
    if os.environ.get("ENVIRONMENT") == "prod":
        return REDIRECT_URIS["prod"]
    return REDIRECT_URIS["dev"]


def is_auth_configured() -> bool:
    """Check if Azure AD authentication is configured."""
    config = _get_config()
    return config is not None


async def handle_login(request: Request) -> RedirectResponse:
    """Handle /auth/login - redirect to Azure AD."""
    config = _get_config()
    if not config:
        return JSONResponse(
            {"error": "Authentication not configured. Contact admin to set up Azure AD."},
            status_code=503,
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state in DynamoDB for multi-instance support
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    _store_oauth_state(
        state_hash,
        {
            "created": datetime.now(timezone.utc).isoformat(),
            "redirect_after": request.query_params.get("redirect", "/"),
        },
    )

    # Build Azure AD authorization URL directly (no network call needed)
    # Include openid and profile for ID token claims
    params = {
        "client_id": config["client_id"],
        "response_type": "code",
        "redirect_uri": get_redirect_uri(),
        "response_mode": "query",
        "scope": "openid profile email User.Read",
        "state": state,
    }
    auth_url = f"{config['authority']}/oauth2/v2.0/authorize?{urlencode(params)}"

    return RedirectResponse(url=auth_url, status_code=302)


async def handle_callback(request: Request) -> RedirectResponse:
    """Handle /auth/callback - exchange code for tokens."""
    import httpx

    config = _get_config()
    if not config:
        return JSONResponse({"error": "Authentication not configured"}, status_code=503)

    # Get authorization code from query params
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        error_description = request.query_params.get("error_description", "Unknown error")
        print(f"[Auth] Azure AD error: {error} - {error_description}")
        return JSONResponse(
            {"error": "Authentication failed", "details": error_description},
            status_code=401,
        )

    if not code or not state:
        return JSONResponse({"error": "Missing code or state"}, status_code=400)

    # Verify state (CSRF protection) - retrieve from DynamoDB
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    session_data = _get_oauth_state(state_hash)
    if not session_data:
        return JSONResponse({"error": "Invalid state - possible CSRF attack"}, status_code=400)

    # Exchange code for tokens using httpx (async)
    print(f"[Auth] Exchanging code for tokens...")
    token_url = f"{config['authority']}/oauth2/v2.0/token"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                token_url,
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code": code,
                    "redirect_uri": get_redirect_uri(),
                    "grant_type": "authorization_code",
                    "scope": "openid profile email User.Read",
                },
            )
            result = response.json()

        if "error" in result:
            print(f"[Auth] Token exchange error: {result.get('error_description')}")
            return JSONResponse(
                {"error": "Token exchange failed", "details": result.get("error_description")},
                status_code=401,
            )

        # Decode the ID token to get user claims (without verification - Azure already verified)
        id_token = result.get("id_token", "")
        if id_token:
            # Decode JWT payload (middle part) without verification
            parts = id_token.split(".")
            if len(parts) >= 2:
                # Add padding if needed
                payload = parts[1]
                payload += "=" * (4 - len(payload) % 4)
                id_token_claims = json.loads(base64.urlsafe_b64decode(payload))
            else:
                id_token_claims = {}
        else:
            id_token_claims = {}

        user_info = {
            "oid": id_token_claims.get("oid"),
            "name": id_token_claims.get("name"),
            "preferred_username": id_token_claims.get("preferred_username"),
            "email": id_token_claims.get("email") or id_token_claims.get("preferred_username"),
        }

        print(f"[Auth] User authenticated: {user_info.get('email')}")

        # Create session token
        session_token = _create_session_token(user_info)

        # Redirect to dashboard with session cookie
        redirect_url = session_data.get("redirect_after", "/")
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key=COOKIE_NAME,
            value=session_token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=True,  # Requires HTTPS
            samesite="lax",
        )
        return response

    except Exception as e:
        print(f"[Auth] Token exchange exception: {e}")
        return JSONResponse({"error": "Authentication failed"}, status_code=500)


async def handle_logout(request: Request) -> RedirectResponse:
    """Handle /auth/logout - clear session and redirect to Azure AD logout."""
    config = _get_config()

    # Clear cookie
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)

    # Optionally redirect to Azure AD logout
    if config:
        logout_url = f"{config['authority']}/oauth2/v2.0/logout"
        params = {"post_logout_redirect_uri": get_redirect_uri().replace("/auth/callback", "/")}
        response = RedirectResponse(url=f"{logout_url}?{urlencode(params)}", status_code=302)
        response.delete_cookie(key=COOKIE_NAME)

    return response


def get_current_user(request: Request) -> Optional[dict]:
    """Extract current user from session cookie."""
    session_token = request.cookies.get(COOKIE_NAME)
    if not session_token:
        return None
    return _verify_session_token(session_token)


async def handle_user_info(request: Request) -> JSONResponse:
    """Handle /api/user - return current user info."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)

    return JSONResponse(
        {
            "authenticated": True,
            "email": user.get("email"),
            "name": user.get("name"),
            "id": user.get("sub"),
        }
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to protect routes with Azure AD authentication."""

    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/health",
        "/auth/login",
        "/auth/callback",
        "/auth/logout",
        "/sse",
        "/messages",
        "/mcp",
        "/api/enhance-alert",  # Internal service-to-service API (VPC only)
    }

    # Path prefixes that don't require authentication
    PUBLIC_PREFIXES = [
        "/sse",
        "/messages",
        "/mcp",
    ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for public prefixes
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Skip auth if not configured (allows development without Azure AD)
        if not is_auth_configured():
            return await call_next(request)

        # Check for valid session
        user = get_current_user(request)
        if not user:
            # For API requests, return 401
            if path.startswith("/api/"):
                return JSONResponse({"error": "Not authenticated"}, status_code=401)

            # For dashboard requests, redirect to login
            # Dashboard is served at root (/) and /dashboard for backwards compatibility
            if path == "/" or path.startswith("/dashboard"):
                login_url = f"/auth/login?redirect={path}"
                return RedirectResponse(url=login_url, status_code=302)

            # For other requests, allow through (static files, etc.)
            return await call_next(request)

        # Add user to request state for downstream handlers
        request.state.user = user
        return await call_next(request)
