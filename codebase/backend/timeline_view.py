"""Adapts studypulse's ExtractedItem-shaped SQLite rows (studypulse/storage.py)
into the FE card shape codebase/FE/src/data.js's `initialEvents` / EventCard.jsx
expect — id/type/title/course/date/time/source/sourceIcon/priority/confidence/
detail/action/verified/due_date_iso/due_time_iso.

Replaces timeline_store.py (deleted — nothing populated it anymore once
/api/v1/chat stopped producing tool_events; mail lands in studypulse's SQLite
via studypulse/mail_ingest.py instead). Only a read/write *shape* adapter,
not a store — studypulse/storage.py is the actual persistence.
"""

from __future__ import annotations

from typing import Any

_CATEGORY_TO_TYPE = {
    "deadline": "deadline",
    "exam": "deadline",
    "assignment": "deadline",
    "schedule": "class",
    "announcement": "announcement",
    "other": "review",
}

_PRIORITY_TO_LABEL = {
    "critical": "Khẩn cấp",
    "high": "Sắp tới",
    "medium": "Bình thường",
    "low": "Cần kiểm tra",
}

# source_platform -> (display name, Material icon, action button label).
# Outlook added here since studypulse/mail_ingest.py ingests it directly —
# the old timeline_store.py's version of this table only knew Gmail/Discord/
# Google Calendar.
_SOURCE = {
    "gmail": ("Gmail", "mail", "Mở email gốc"),
    "outlook": ("Outlook", "mail", "Mở email Outlook gốc"),
    "discord": ("Discord", "forum", "Đi tới Discord"),
    "direct_input": ("Google Calendar", "calendar_month", "Mở lịch gốc"),
}
_DEFAULT_SOURCE = ("Gmail", "mail", "Mở email gốc")


def to_card(item: dict[str, Any]) -> dict[str, Any]:
    """One studypulse timeline item -> one FE EventCard-shaped dict."""
    platform = item.get("source_platform", "")
    source, source_icon, action = _SOURCE.get(platform, _DEFAULT_SOURCE)

    # due_date_iso/due_time_iso win if the FE has already PATCHed this item
    # (patch bodies use those key names) — else fall back to studypulse's
    # own due_date/due_time from extraction.
    due_date_iso = item.get("due_date_iso") or item.get("due_date") or ""
    due_time_iso = item.get("due_time_iso") or item.get("due_time") or ""

    confidence_score = item.get("confidence_score", 0.0) or 0.0
    # Only >=0.85-confidence items ever reach SQLite (route_by_confidence
    # in studypulse/graph.py routes anything lower to hitl_escalation
    # instead of dashboard_sync) — so "verified" defaults true here unless
    # explicitly overridden by a PATCH.
    verified = item.get("verified")
    if verified is None:
        verified = confidence_score >= 0.85

    return {
        "id": item.get("id", ""),
        "type": _CATEGORY_TO_TYPE.get(item.get("category", "other"), "review"),
        "title": item.get("title", ""),
        "course": item.get("course", ""),
        "date": item.get("date") or due_date_iso or "Chờ xác nhận",
        "time": item.get("time") or due_time_iso or "—",
        "source": source,
        "sourceIcon": source_icon,
        "priority": _PRIORITY_TO_LABEL.get(item.get("priority", "medium"), "Bình thường"),
        "confidence": round(confidence_score * 100),
        "detail": item.get("description", ""),
        "action": action,
        "verified": bool(verified),
        "due_date_iso": due_date_iso,
        "due_time_iso": due_time_iso,
        # Original message text this item was extracted from, for the
        # in-app source-toggle button (EventCard.jsx) — and, separately,
        # source_url: a real deep link to the original message/channel when
        # the ingesting module could build one (see mail_ingest.py /
        # discord_ingest.py). Empty for direct_input or anything ingested
        # before source_url existed on ExtractedItem.
        "raw_snippet": item.get("raw_snippet", ""),
        "source_url": item.get("source_url", ""),
    }
