"""Tools the RAG chatbot LLM can call mid-conversation, instead of always
being handed one fixed FAISS similarity_search(k=3) + the last 10 timeline
items regardless of what was actually asked (the old rag_chatbot_node
shape). Two tools, covering the two ways a question narrows down "which
timeline items":

- search_timeline: semantic/topical — "anything about the AI hackathon",
  "important stuff" — embedding similarity over title+description+category.
- query_timeline: structured/exact — "what's on Gmail", "just exam dates",
  "only critical priority" — a plain SQL filter, which similarity search
  handles poorly since platform/category/priority aren't semantic content,
  they're metadata. This is exactly the shape "trong gmail thì sao?" (a
  follow-up narrowing an earlier answer to one platform) needs.

Both return the same compact item shape so the calling node can accumulate
sources_cited/timeline_items_referenced identically regardless of which
tool produced a given item.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

RAG_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_timeline",
            "description": (
                "Semantic search over ingested timeline items (deadlines, exams, "
                "assignments, announcements) and course materials. Use for topical "
                "or vague questions — e.g. 'anything important', 'what's the AI "
                "hackathon about'. Not filtered by platform/category — for that, "
                "use query_timeline instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query."},
                    "k": {"type": "integer", "description": "Max results (default 5).", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_timeline",
            "description": (
                "Exact filtered lookup of timeline items straight from the database. "
                "Use when the question names a specific source platform, category, or "
                "priority — e.g. 'what's on Gmail', 'just exams', 'anything critical' — "
                "including follow-ups that narrow a prior answer this way ('trong gmail "
                "thì sao?' after a general question). At least one filter should be set; "
                "omit a field to leave it unfiltered."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_platform": {"type": "string", "enum": ["gmail", "outlook", "discord", "direct_input"]},
                    "category": {
                        "type": "string",
                        "enum": ["deadline", "schedule", "assignment", "announcement", "exam", "other"],
                    },
                    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "limit": {"type": "integer", "description": "Max results (default 10).", "default": 10},
                },
            },
        },
    },
]


def _item_label(item: dict[str, Any]) -> str:
    platform = item.get("source_platform", "")
    title = item.get("title", "")
    if platform == "gmail":
        return f"Email: {title}" if title else "Email gốc"
    if platform == "outlook":
        return f"Email Outlook: {title}" if title else "Email Outlook gốc"
    return title or "Nguồn không xác định"


def items_to_citations(items: list[dict[str, Any]]) -> list[tuple[str, dict[str, str]]]:
    """(item_id, citation) pairs for a batch of raw item dicts, whichever
    tool produced them — same label rules the old inline FAISS-metadata
    citation logic used. One entry per item (item_id may be ""), so callers
    can dedupe by id without the two halves drifting out of sync. Skips the
    FAISS seed/bootstrap placeholder (vector_store.py's _fallback_docs) —
    it's synthetic filler for an empty index, not a real citable source."""
    return [
        (item.get("item_id") or item.get("id", ""), {"label": _item_label(item), "url": ""})
        for item in items
        if item.get("source") != "seed"
    ]


def _compact(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim each item to what the LLM needs to answer + cite, not the full
    ExtractedItem/FAISS-metadata shape (raw_snippet, embeddings-adjacent
    fields, etc.) — keeps tool results cheap across multiple rounds."""
    return [
        {
            "id": item.get("item_id") or item.get("id", ""),
            "title": item.get("title", ""),
            "category": item.get("category") or item.get("type", ""),
            "due_date": item.get("due_date", ""),
            "due_time": item.get("due_time", ""),
            "priority": item.get("priority", ""),
            "source_platform": item.get("source_platform", ""),
            "description": item.get("description", "")[:300],
        }
        for item in items
    ]


def execute_rag_tool(name: str, args: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Run one tool call. Returns (text to feed back to the LLM, raw items
    for the caller's citation bookkeeping). Never raises — a broken tool
    call becomes an error string the LLM sees and can react to, same as the
    old chat.py agent loop's execute_tool_call."""
    try:
        if name == "search_timeline":
            from .vector_store import get_vector_store

            query = args.get("query", "")
            k = int(args.get("k") or 5)
            items = get_vector_store().similarity_search_with_metadata(query, k=k)
        elif name == "query_timeline":
            from .storage import get_db

            db = get_db()
            filters = {
                "source_platform": args.get("source_platform"),
                "category": args.get("category"),
                "priority": args.get("priority"),
            }
            limit = int(args.get("limit") or 10)
            items = db.query_timeline(limit=limit, **filters)
            # A model call regularly over-filters — e.g. carrying a
            # "priority=critical" reading of an earlier turn's "important"
            # into a follow-up that only actually narrowed by platform (see
            # nodes.py's rag_chatbot_node docstring / the "trong gmail thì
            # sao?" case this was built for). Rather than depend on the
            # model reliably retrying with fewer filters itself (prompt
            # guidance alone wasn't enough), drop the vaguer, more
            # inference-prone filters deterministically on an empty result:
            # priority (a loose word like "important" rarely maps cleanly to
            # critical/high/medium/low) then category. source_platform is
            # deliberately never auto-dropped — when a model sets it, it's
            # almost always a literal platform name the user actually said
            # (e.g. "gmail"), not an inference, so silently ignoring it
            # would answer a different question than the one asked.
            for field in ("priority", "category"):
                if items or filters.get(field) is None:
                    continue
                filters = {**filters, field: None}
                items = db.query_timeline(limit=limit, **filters)
        else:
            return json.dumps({"error": "unknown_tool", "message": f"No tool named {name}"}), []
    except Exception as exc:
        logger.warning(f"RAG tool '{name}' failed: {exc}")
        return json.dumps({"error": type(exc).__name__, "message": str(exc)}), []

    compacted = _compact(items)
    if not compacted:
        return json.dumps({"results": [], "message": "No matching items."}), []
    return json.dumps({"results": compacted}, ensure_ascii=False), items
