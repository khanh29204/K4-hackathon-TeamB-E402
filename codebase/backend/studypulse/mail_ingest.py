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
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
import re
from mcp_bridge.gmail_client import call_gmail_tool
from mcp_bridge.outlook_client import call_tool_text as outlook_call_tool_text

from .graph import get_compiled_graph
from .state import SourcePlatform

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30
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
    """Recent Gmail threads via search_threads."""
    try:
        text = asyncio.run(call_gmail_tool(
            "search_threads",
            {"query": f"newer_than:{days}d", "max_results": str(max_results), "output": "json"},
        ))
        try:
            threads = json.loads(text)
            if isinstance(threads, list):
                return [
                    {
                        "message_id": t.get("thread_id", t.get("id", "")),
                        "subject": t.get("subject", ""),
                        "from": t.get("from", ""),
                        "body_preview": t.get("snippet", t.get("body_preview", "")),
                        "received_at": t.get("date", t.get("received_at", "")),
                        "is_unread": bool(t.get("is_unread", True)),
                    }
                    for t in threads
                ]
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback text parsing if output was formatted string from _fallback_search_threads
        results = []
        blocks = text.split("\n- ")
        for block in blocks:
            if "thread_id:" not in block and "Thread ID:" not in block:
                continue
            lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
            header_line = lines[0] if lines else ""
            t_match = re.search(r"(?:thread_id|Thread ID):\s*([a-f0-9]+)", header_line, re.IGNORECASE)
            thread_id = t_match.group(1) if t_match else ""
            subj_match = re.search(r"Tiêu đề:\s*(.*?)(?:\n|$)|^\*\*(.*?)\*\*", block)
            subject = (subj_match.group(1) or subj_match.group(2)) if subj_match else "Gmail Email"
            from_match = re.search(r"Từ:\s*(.*?)(?:\n|$)|from\s+\"?(.*?)\"?\s*·", block)
            sender = (from_match.group(1) or from_match.group(2)) if from_match else "Gmail User"
            
            snippet = block
            results.append({
                "message_id": thread_id,
                "subject": subject.strip(),
                "from": sender.strip(),
                "body_preview": snippet,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "is_unread": True,
            })
        return results
    except Exception as exc:
        logger.error("Failed to fetch gmail messages: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════
# PREFILTER — deterministic, zero LLM cost
# ═══════════════════════════════════════════════════════════════════════════

def prefilter(messages: list[dict[str, Any]], *, unread_only: bool = True) -> list[dict[str, Any]]:
    """Filter messages: exclude generic marketing/promotional spam and apply read-state rules."""
    promo_keywords = ["khuyến mãi", "ưu đãi", "promotion", "discount", "newsletter", "unsubscribed", "đăng ký ngay"]
    filtered = []
    for m in messages:
        if unread_only and not m.get("is_unread"):
            continue
        subj = (m.get("subject") or "").lower()
        if any(kw in subj for kw in promo_keywords):
            continue
        filtered.append(m)
    return filtered


# ═══════════════════════════════════════════════════════════════════════════
# FULL BODY — only for messages that survive the prefilter, same
# "search then read" two-step shape as the chat tools (outlook_mail_read /
# gmail_read_thread), just called from ingestion instead of the LLM.
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_outlook_body(message_id: str) -> str:
    text = asyncio.run(outlook_call_tool_text(
        "mail",
        {"operation": "get_message", "message_id": message_id, "output": "raw"},
    ))
    data = json.loads(text)
    return (data.get("body") or {}).get("content", "") or data.get("bodyPreview", "")


def _fetch_gmail_body(thread_id: str) -> str:
    return asyncio.run(call_gmail_tool("get_thread", {"thread_id": thread_id}))
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

def _ingest_one(message: dict[str, Any], source: str, user_id: str | None = None) -> dict[str, Any]:
    """One message through the compiled graph's ingestion flow (extraction
    -> validation -> confidence gate -> SQLite/FAISS, or HITL if
    low-confidence) — same path scheduler.py uses for emergency_alert."""
    body = _fetch_full_body(message, source) or message.get("body_preview", "")
    uid = user_id or "default_user"
    raw_payload = {
        "source_platform": source,
        "message_id": message.get("message_id", ""),
        "body": body,
        "subject": message.get("subject", ""),
        "from": message.get("from", ""),
        "received_at": message.get("received_at", ""),
        "user_id": uid,
    }
    state = {"flow_type": "ingestion", "raw_payload": raw_payload}
    config = {"configurable": {"thread_id": f"ingest_{uid}_{source}_{message.get('message_id', '')}"}}
    return get_compiled_graph().invoke(state, config=config)


def ingest_new_mail(source: str, *, days: int = DEFAULT_LOOKBACK_DAYS, unread_only: bool = True, user_id: str | None = None) -> dict[str, Any]:
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
            _ingest_one(message, source, user_id=user_id)
            ingested += 1
        except Exception:
            logger.exception("Failed to ingest %s message %s", source, message.get("message_id"))
            errors += 1

    result = {"source": source, "fetched": len(fetched), "prefiltered": len(survivors), "ingested": ingested, "errors": errors}
    logger.info("Mail ingestion complete: %s", result)
    return result


def trigger_ingestion_async(source: str, **kwargs: Any) -> None:
    """Fire-and-forget: run ingest_new_mail in a background thread so the
    caller (a connection-success handler) doesn't block its HTTP response
    on a mailbox sync + LLM classification pass."""
    thread = threading.Thread(target=ingest_new_mail, args=(source,), kwargs=kwargs, daemon=True)
    thread.start()
