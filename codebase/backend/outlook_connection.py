"""Outlook connection status and sign-in for the "Quản lý kết nối" UI.

Unlike the unified Google connection, there's no OAuth handshake this
backend drives directly — outlook-local-mcp's Docker container owns its own
account registry and device-code sign-in (see codebase/mcp/outlook_mcp/README.md).
The container itself now runs on a separate machine behind the Outlook bridge
(codebase/mcp/outlook_bridge), reached over HTTP via mcp_bridge.outlook_client
— this module no longer holds any session open itself, every call here is a
fresh, stateless request to that bridge.

get_status() is a passive, no-Graph-call read of that registry (`system.status`)
for the connections panel's dot/label. It's best-effort: if the bridge/tunnel
isn't reachable, it reports disconnected rather than raising.

start_connect()/get_connect_status() are the real sign-in trigger, wired to
the panel's "Connect" button. start_connect() kicks off a background thread
that polls the bridge every few seconds for up to ~15 minutes (matching the
device code's own expiry) and returns quickly with either "already connected"
or the device-code text to show the user; the FE polls get_connect_status()
for the rest of the wait.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from mcp_bridge.outlook_client import call_tool_text
from studypulse.mail_ingest import trigger_ingestion_async

# The exact prefix of the message outlook-local-mcp's device-code fallback
# returns as normal (non-error) tool text when no cached token is valid yet
# (see internal/auth/middleware.go's presentDeviceCode) — used to tell "still
# needs sign-in" apart from a real calendar list in the same text field.
DEVICE_CODE_MARKER = "To sign in, use a web browser"

# While the background auth goroutine (inside the container the bridge is
# holding open) hasn't finished yet, every retry deliberately comes back as
# an MCP *error* result containing this substring (see internal/auth/middleware.go's
# pendingAuthMessage / "still in progress" — asserted verbatim by the
# vendored project's own tests). That's expected mid-wait, not a real
# failure — only an error NOT containing this substring means something
# actually went wrong.
STILL_IN_PROGRESS_MARKER = "still in progress"

POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 15 * 60  # matches the device code's own ~15 min expiry
STARTUP_WAIT_SECONDS = 10  # how long start_connect() blocks for the initial response

_state_lock = threading.Lock()
_state: dict[str, Any] = {"status": "idle", "message": ""}


def get_status() -> dict[str, Any]:
    try:
        raw = asyncio.run(call_tool_text("system", {"operation": "status", "output": "summary"}))
        payload = json.loads(raw)
    except Exception:
        return {"connected": False, "accounts": []}
    accounts = payload.get("accounts", [])
    connected = any(account.get("authenticated") for account in accounts)
    return {"connected": connected, "accounts": accounts}


def _set_state(status: str, message: str = "") -> None:
    with _state_lock:
        _state["status"] = status
        _state["message"] = message


def get_connect_status() -> dict[str, Any]:
    with _state_lock:
        return dict(_state)


async def _probe() -> tuple[bool, str]:
    """One calendar probe against the bridge. Returns (still_waiting, text) —
    still_waiting is True both for the initial device-code prompt and for the
    "still in progress" retries; only a genuinely different error raises."""
    try:
        text = await call_tool_text("calendar", {"operation": "list_calendars"})
    except RuntimeError as exc:
        message = str(exc)
        if STILL_IN_PROGRESS_MARKER in message:
            return True, message
        raise
    return text.startswith(DEVICE_CODE_MARKER), text


def _connect_flow() -> None:
    """Runs on its own background thread, spawned by start_connect(). Each
    probe is an independent HTTP call to the bridge — the persistent
    container session lives there now, not in this process."""
    try:
        waiting, text = asyncio.run(_probe())
        if not waiting:
            _set_state("connected", "Outlook đã kết nối.")
            trigger_ingestion_async("outlook")
            return

        _set_state("pending", text)
        waited = 0
        while waited < MAX_WAIT_SECONDS:
            time.sleep(POLL_INTERVAL_SECONDS)
            waited += POLL_INTERVAL_SECONDS
            waiting, _ = asyncio.run(_probe())
            if not waiting:
                _set_state("connected", "Đã đăng nhập Outlook thành công.")
                trigger_ingestion_async("outlook")
                return
        _set_state("timeout", "Hết thời gian chờ đăng nhập Outlook — bấm Kết nối để thử lại.")
    except Exception as exc:
        _set_state("failed", str(exc))


def start_connect() -> dict[str, Any]:
    """Trigger (or check on) an Outlook sign-in. Returns quickly once the
    initial response is known — either already connected, or the device-code
    text to show the user — without waiting for the full sign-in wait.

    A prior "connected" result is trusted as-is rather than re-verified,
    deliberately: re-checking would mean an extra round-trip to the bridge
    just to ask, and the actual mail/calendar tool calls will surface it
    plainly if the token has since gone stale (same as any other Outlook
    tool call)."""
    with _state_lock:
        if _state["status"] in ("starting", "pending", "connected"):
            return dict(_state)
        _state["status"] = "starting"
        _state["message"] = ""

    threading.Thread(target=_connect_flow, daemon=True).start()

    for _ in range(int(STARTUP_WAIT_SECONDS / 0.5)):
        time.sleep(0.5)
        with _state_lock:
            if _state["status"] != "starting":
                return dict(_state)
    return get_connect_status()


async def _logout_default_account_safe() -> None:
    # Best-effort: clears the cached tokens for the "default" account so a
    # future connect actually re-prompts instead of silently reusing what the
    # bridge's still-open container remembers. Doesn't revoke the OAuth grant
    # with Microsoft (see account.logout's own docs) — only local state.
    try:
        await call_tool_text("account", {"operation": "logout", "label": "default"})
    except Exception:
        pass  # bridge unreachable, or nothing to log out — fine either way


def disconnect() -> None:
    """Clear the Outlook sign-in: log the account out server-side (clears its
    cached tokens) so the next "Connect" click properly re-prompts."""
    asyncio.run(_logout_default_account_safe())
    _set_state("idle", "")
