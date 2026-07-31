"""Unified Google OAuth connection shared by the Calendar tools and gmail_mcp.
One consent screen grants both Gmail and Calendar scopes; the resulting token
is written to codebase/backend/credentials/token.json.

gmail_mcp is a separate local MCP server process that reads this same file
directly (point its GOOGLE_CALENDAR_TOKEN_FILE / GOOGLE_CLIENT_SECRETS_FILE
env vars at this directory — see codebase/mcp/.env.example) instead of running
its own separate OAuth handshake. Calendar needs no local server at all: the
backend calls Google's hosted Calendar MCP server with the token loaded here
(see mcp_bridge/google_calendar_client.py).

Setup: create an OAuth client (Application type: Web application) in Google
Cloud Console with redirect URI matching GOOGLE_OAUTH_REDIRECT_URI (default
http://localhost:8000/api/v1/connections/google/callback), download its JSON,
and save it at the path CLIENT_SECRETS_FILE resolves to below.

NOTE: if a token.json predates the Calendar-MCP scopes added to SCOPES below,
it was granted fewer scopes than the MCP server requires and Calendar calls
will fail with a permission error. Disconnect and reconnect in the FE
("Quản lý kết nối" > Gmail) to re-consent with the full list.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

_CREDENTIALS_DIR = Path(__file__).resolve().parent / "credentials"

SCOPES = [
    # Full Calendar access — needed for the write tools (create_event) that
    # Google's Calendar MCP server exposes.
    "https://www.googleapis.com/auth/calendar",
    # The three scopes Google's Calendar MCP server documents for itself.
    # `.../auth/calendar` above is a superset of the read ones, but the MCP
    # server checks for these specific scopes, so request them explicitly.
    # https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def client_secrets_path() -> Path:
    env_path = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRETS_FILE")
    if env_path:
        return Path(env_path)
    
    target = _CREDENTIALS_DIR / "client_secret.json"
    if not target.exists():
        # Fallback to gmail_secret.json in workspace root if client_secret.json is missing
        workspace_root_secret = _CREDENTIALS_DIR.parent.parent / "gmail_secret.json"
        if workspace_root_secret.exists():
            _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(workspace_root_secret.read_text(encoding="utf-8"), encoding="utf-8")
            
    return target


def token_path(user_email: str | None = None) -> Path:
    if user_email:
        safe_name = re.sub(r"[^\w\.-]", "_", user_email)
        user_target = _CREDENTIALS_DIR / "tokens" / f"{safe_name}.json"
        if user_target.exists():
            return user_target
    default_target = _CREDENTIALS_DIR / "token.json"
    env_path = os.environ.get("GOOGLE_CALENDAR_TOKEN_FILE")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        # If p doesn't exist relative to CWD, try resolving filename inside _CREDENTIALS_DIR
        candidate = _CREDENTIALS_DIR / p.name
        if candidate.exists():
            return candidate
    return default_target


def redirect_uri() -> str:
    return os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/connections/google/callback")


class GoogleConnectionError(RuntimeError):
    pass


def _build_flow() -> Flow:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    secrets_path = client_secrets_path()
    if not secrets_path.exists():
        raise GoogleConnectionError(
            f"Missing Google OAuth client secrets at {secrets_path}. Create a Web application "
            f"OAuth client in Google Cloud Console (redirect URI {redirect_uri()}), download its "
            "JSON and save it at that path."
        )
    return Flow.from_client_secrets_file(str(secrets_path), scopes=SCOPES, redirect_uri=redirect_uri())


# Flow.authorization_url() auto-generates a PKCE code_verifier that lives only
# on that Flow instance. The callback arrives as a separate HTTP request, so
# the flow that issued the auth URL must be kept around to complete the
# exchange with the matching verifier — a fresh Flow() here has no verifier
# and Google rejects the token exchange. Single global is fine: this backend
# runs as one uvicorn process for one operator, same assumption the rest of
# this codebase's token storage already makes.
_pending_flow: Flow | None = None


def get_authorization_url() -> str:
    global _pending_flow
    flow = _build_flow()
    auth_url, _state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    _pending_flow = flow
    return auth_url


def exchange_code(code: str) -> None:
    global _pending_flow
    flow = _pending_flow or _build_flow()
    flow.fetch_token(code=code)
    _pending_flow = None
    _save(flow.credentials)


def _save(creds: Credentials) -> None:
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text(creds.to_json(), encoding="utf-8")


def load_credentials() -> Credentials | None:
    """Return valid credentials for the shared Google connection, refreshing
    the stored token if needed. None if never connected."""
    path = token_path()
    if not path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(path))
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save(creds)
            return creds
    except Exception as exc:
        logging.warning("Failed to load/refresh Google credentials (%s)", exc)
        return None
    return None


def disconnect() -> None:
    token_path().unlink(missing_ok=True)


def get_status() -> dict[str, Any]:
    creds = load_credentials()
    if creds is None:
        return {"connected": False, "email": None, "scopes": []}
    email = None
    try:
        response = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=5.0,
        )
        if response.status_code == 200:
            email = response.json().get("email")
    except httpx.HTTPError:
        pass
    return {"connected": True, "email": email, "scopes": list(creds.scopes or [])}
