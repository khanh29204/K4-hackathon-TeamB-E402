"""Mail ingestion: fetch recent Gmail/Outlook messages, prefilter by date +
read state, and feed survivors through the studypulse ingestion graph so
they get classified (priority/category), persisted to SQLite, and indexed
into FAISS — the same data daily_reminder_node/rag_chatbot_node read from.

Triggered right after a mailbox connects (see server.py's Google OAuth
callback and outlook_connection._connect_flow's "connected" transitions),
not on a timer — this module only fetches/classifies what's new since the
account was last synced, it doesn't itself schedule anything.

Fetch, not "search then read": both providers' list/summary endpoints
already return subject + a body preview + isRead + received-at in one call
(see mail-rag-design artifact's corrected 3b — Outlook's list_messages
already supports output=summary/raw and start_datetime/end_datetime
natively; Gmail's search_threads was extended with output=json for the
same reason), so the prefilter runs on that before any LLM spend, and only
survivors get a follow-up full-body fetch.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from mcp_bridge.http_mcp_client import call_tool_text as gmail_call_tool_text
from mcp_bridge.outlook_client import call_tool_text as outlook_call_tool_text
from tools._shared import GMAIL_MCP_URL

from . import ingest_status
from .graph import get_compiled_graph
from .state import SourcePlatform

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_MAX_RESULTS = 25


# ═══════════════════════════════════════════════════════════════════════════
# FETCH — structured, one call per provider, no LLM involved
# ═══════════════════════════════════════════════════════════════════════════

def fetch_outlook_messages(
    days: int = DEFAULT_LOOKBACK_DAYS,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Recent Outlook messages via list_messages(output=summary), which
    already carries isRead/receivedDateTime — see module docstring."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    text = asyncio.run(outlook_call_tool_text(
        "mail",
        {
            "operation": "list_messages",
            "output": "summary",
            "start_datetime": start,
            "end_datetime": end,
            "max_results": max_results,
        },
    ))
    messages = json.loads(text)
    return [
        {
            "message_id": m.get("id", ""),
            "subject": m.get("subject", ""),
            "from": (m.get("from") or {}).get("address", ""),
            "body_preview": m.get("bodyPreview", ""),
            "received_at": m.get("receivedDateTime", ""),
            "is_unread": not m.get("isRead", True),
        }
        for m in messages
    ]


def fetch_gmail_messages(
    days: int = DEFAULT_LOOKBACK_DAYS,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Recent Gmail threads via search_threads(output="json") — see
    codebase/mcp/gmail_mcp/tools.py's _thread_summary_json."""
    text = asyncio.run(gmail_call_tool_text(
        GMAIL_MCP_URL,
        "search_threads",
        {"query": f"newer_than:{days}d", "max_results": str(max_results), "output": "json"},
    ))
    threads = json.loads(text)
    return [
        {
            "message_id": t.get("thread_id", ""),
            "subject": t.get("subject", ""),
            "from": t.get("from", ""),
            "body_preview": t.get("snippet", ""),
            "received_at": t.get("date", ""),
            "is_unread": bool(t.get("is_unread", False)),
        }
        for t in threads
    ]


# ═══════════════════════════════════════════════════════════════════════════
# PREFILTER — deterministic, zero LLM cost
# ═══════════════════════════════════════════════════════════════════════════

def prefilter(messages: list[dict[str, Any]], *, unread_only: bool = False) -> list[dict[str, Any]]:
    """Date window is already applied at fetch time (start_datetime/
    newer_than); this is the read-state half of the prefilter. Defaults to
    OFF: a student can easily have already read an important email (a
    deadline notice, a schedule change) without StudyPulse ever indexing it
    otherwise, which defeats "what's important" queries over exactly the
    mail the student already opened. Set unread_only=True to opt back into
    the old unread-only behavior (cheaper — fewer LLM classification calls
    per sync) if inbox volume ever makes that worth trading off."""
    if not unread_only:
        return messages
    return [m for m in messages if m.get("is_unread")]


# ═══════════════════════════════════════════════════════════════════════════
# FULL BODY — only for messages that survive the prefilter, same
# "search then read" two-step shape as the chat tools (outlook_mail_read /
# gmail_read_thread), just called from ingestion instead of the LLM.
# ═══════════════════════════════════════════════════════════════════════════

_HTML_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)
_HTML_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def _html_to_text(raw_html: str) -> str:
    """Same approach as gmail_mcp/tools.py's _html_to_text — duplicated
    rather than imported since that lives in a separate MCP server package
    (codebase/mcp/gmail_mcp), not this backend."""
    text = _HTML_TAG_RE.sub("\n", raw_html)
    text = html.unescape(text)
    return _HTML_BLANK_LINES_RE.sub("\n\n", text).strip()


def _fetch_outlook_body(message_id: str) -> str:
    text = asyncio.run(outlook_call_tool_text(
        "mail",
        {"operation": "get_message", "message_id": message_id, "output": "raw"},
    ))
    data = json.loads(text)
    body = data.get("body") or {}
    content = body.get("content", "") or data.get("bodyPreview", "")
    # Graph API defaults to HTML (body.contentType == "html") unless the
    # caller sends a Prefer: outlook.body-content-type="text" header, which
    # this MCP tool doesn't — unlike gmail_mcp's get_thread (which already
    # strips HTML itself), so raw markup would otherwise flow straight into
    # PII masking / extraction / the "Xem nguồn gốc" raw_snippet display.
    if body.get("contentType", "").lower() == "html" and content:
        return _html_to_text(content)
    return content


def _fetch_gmail_body(thread_id: str) -> str:
    # get_thread has no output=json mode (it's a free-text summary of every
    # message in the thread) — that's fine, ai_extraction_node's prompt
    # takes free text either way.
    return asyncio.run(gmail_call_tool_text(GMAIL_MCP_URL, "get_thread", {"thread_id": thread_id}))


def _fetch_full_body(message: dict[str, Any], source: str) -> str:
    try:
        if source == SourcePlatform.OUTLOOK.value:
            return _fetch_outlook_body(message.get("message_id", ""))
        return _fetch_gmail_body(message.get("message_id", ""))
    except Exception:
        logger.warning(
            "Full-body fetch failed for %s message %s, falling back to preview",
            source, message.get("message_id"), exc_info=True,
        )
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# INGEST — run survivors through the studypulse ingestion flow
# ═══════════════════════════════════════════════════════════════════════════

def _mail_url(message_id: str, source: str) -> str:
    """Deep link back to the original message — built here, not later at
    display time, since this is the one place a bare Graph/Gmail id is still
    unambiguously tied to its provider. Gmail's id is a thread_id (see
    fetch_gmail_messages); Outlook's is a Graph message id needing URL
    encoding (it routinely contains '/' and '+')."""
    if not message_id:
        return ""
    if source == SourcePlatform.GMAIL.value:
        return f"https://mail.google.com/mail/u/0/#all/{message_id}"
    if source == SourcePlatform.OUTLOOK.value:
        return f"https://outlook.office.com/mail/deeplink/read/{quote(message_id, safe='')}"
    return ""


def _ingest_one(message: dict[str, Any], source: str) -> dict[str, Any]:
    """One message through the compiled graph's ingestion flow (extraction
    -> validation -> confidence gate -> SQLite/FAISS, or HITL if
    low-confidence) — same path scheduler.py uses for emergency_alert."""
    body = _fetch_full_body(message, source) or message.get("body_preview", "")
    raw_payload = {
        "source_platform": source,
        "message_id": message.get("message_id", ""),
        "source_url": _mail_url(message.get("message_id", ""), source),
        "body": body,
        "subject": message.get("subject", ""),
        "from": message.get("from", ""),
        "received_at": message.get("received_at", ""),
    }
    state = {"flow_type": "ingestion", "raw_payload": raw_payload}
    config = {"configurable": {"thread_id": f"ingest_{source}_{message.get('message_id', '')}"}}
    return get_compiled_graph().invoke(state, config=config)


def ingest_new_mail(source: str, *, days: int = DEFAULT_LOOKBACK_DAYS, unread_only: bool = False) -> dict[str, Any]:
    """Fetch -> prefilter -> ingest for one provider. Returns counts, not
    raw state, so callers (the connection-trigger hooks, or a manual
    re-sync endpoint later) don't need to know studypulse's internals."""
    if source == SourcePlatform.GMAIL.value:
        fetched = fetch_gmail_messages(days=days)
    elif source == SourcePlatform.OUTLOOK.value:
        fetched = fetch_outlook_messages(days=days)
    else:
        raise ValueError(f"Unknown mail source: {source!r}")

    survivors = prefilter(fetched, unread_only=unread_only)
    ingested = 0
    errors = 0
    for message in survivors:
        try:
            _ingest_one(message, source)
            ingested += 1
        except Exception:
            logger.exception("Failed to ingest %s message %s", source, message.get("message_id"))
            errors += 1

    result = {"source": source, "fetched": len(fetched), "prefiltered": len(survivors), "ingested": ingested, "errors": errors}
    logger.info("Mail ingestion complete: %s", result)
    return result


def _ingest_and_track(source: str, **kwargs: Any) -> None:
    ingest_status.set_status(source, "running")
    try:
        result = ingest_new_mail(source, **kwargs)
        # ingest_new_mail's own result dict already carries a "source" key
        # (see its return statement) — spreading it verbatim collides with
        # the positional `source` set_status also takes.
        ingest_status.set_status(source, "done", **{k: v for k, v in result.items() if k != "source"})
    except Exception as exc:
        logger.exception("Mail ingestion failed for %s", source)
        ingest_status.set_status(source, "error", error=str(exc))


def trigger_ingestion_async(source: str, **kwargs: Any) -> None:
    """Fire-and-forget: run ingest_new_mail in a background thread so the
    caller (a connection-success handler) doesn't block its HTTP response
    on a mailbox sync + LLM classification pass. Progress is recorded in
    ingest_status for the FE to poll (see that module's docstring)."""
    thread = threading.Thread(target=_ingest_and_track, args=(source,), kwargs=kwargs, daemon=True)
    thread.start()
