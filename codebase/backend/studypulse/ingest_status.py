"""In-memory ingestion progress, keyed by source ("gmail"/"outlook"/"discord").

mail_ingest.trigger_ingestion_async and discord_ingest.trigger_guild_ingestion_async
are fire-and-forget background threads with no result the caller (an OAuth
callback / connect-status poll loop) can hand back in its own HTTP response.
This module gives the FE somewhere to poll instead — GET
/api/v1/connections/ingest-status (server.py) — so "Quản lý kết nối" can show
a "đang tải..." state right after a mailbox/guild connects instead of the
timeline just silently filling in whenever the background thread finishes.

Process-local and unbounded history is not a goal: each source only ever
holds its most recent run's status, matching outlook_connection.py's _state
pattern for the same reason (single backend process, single browser tab).
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_status: dict[str, dict[str, Any]] = {}


def set_status(source: str, status: str, **extra: Any) -> None:
    with _lock:
        _status[source] = {"status": status, **extra}


def get_status(source: str) -> dict[str, Any]:
    with _lock:
        return dict(_status.get(source, {"status": "idle"}))


def get_all() -> dict[str, dict[str, Any]]:
    with _lock:
        return {source: dict(value) for source, value in _status.items()}
