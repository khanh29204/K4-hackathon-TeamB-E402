"""Tools the RAG chatbot LLM can call mid-conversation, instead of always
being handed one fixed FAISS similarity_search(k=3) + the last 10 timeline
items regardless of what was actually asked (the old rag_chatbot_node
shape).

- search_timeline: semantic/topical — "anything about the AI hackathon",
  "important stuff" — embedding similarity over title+description+category.
- query_timeline: structured/exact — "what's on Gmail", "just exam dates",
  "only critical priority" — a plain SQL filter, which similarity search
  handles poorly since platform/category/priority aren't semantic content,
  they're metadata. This is exactly the shape "trong gmail thì sao?" (a
  follow-up narrowing an earlier answer to one platform) needs.
- list_calendar_events: a DIFFERENT data source entirely — the student's
  actual Google/Outlook Calendar, reached via the same TOOL_FUNCTIONS
  tools/calendar_create_event.py's confirm_calendar endpoint writes into,
  not studypulse's SQLite/FAISS. search_timeline/query_timeline only ever
  see items extracted from ingested mail/Discord; a real calendar event
  (e.g. one the student created themselves, or one already confirmed onto
  the calendar) never lands in timeline_items, so "do I have any meetings
  today" needs this tool or it always comes back empty.
- gmail_search/gmail_read_thread, outlook_mail_search/outlook_mail_read,
  discord_find_channel/discord_read_messages/discord_list_guilds/
  discord_server_info/discord_list_channels: LIVE lookups against the
  mailbox/Discord server itself, via the same TOOL_FUNCTIONS the pre-
  langgraph chat.py agent used (see tools/__init__.py) — not studypulse's
  SQLite/FAISS. Closes a known, explicitly-documented gap from that
  migration (see server.py's /api/v1/chat docstring): search_timeline/
  query_timeline only ever see what a background ingestion pass already
  extracted as a deadline/exam/etc — mail outside the ingestion lookback
  window, a specific message the student wants read in full, or Discord
  history in a channel/guild that was never (or not yet) ingested are all
  invisible to those two tools and need a live call instead. Read-only.
- create_calendar_event: the one WRITE tool here — creates a real Google
  Calendar event. Gated by the underlying tool itself (TOOL_FUNCTIONS'
  calendar_create_event, also used by server.py's confirm_calendar/"Thêm
  vào lịch" button): called with confirmed omitted/false it does nothing
  but describe what it *would* create, called with confirmed=true it
  actually writes the event. rag_chatbot_node's tool loop has no
  pause/resume (interrupt) mechanism the way hitl_escalation does for
  ingestion, so the confirm step has to span two separate /api/v1/chat
  turns instead of one — see RAG_AGENT_TOOL_GUIDANCE for the exact
  two-turn protocol this relies on.

search_timeline/query_timeline return the same compact item shape so the
calling node can accumulate sources_cited/timeline_items_referenced
identically regardless of which one produced a given item; none of the
other tools above participate in that (see execute_rag_tool).
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
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": (
                "List events actually on the student's Google or Outlook Calendar in a time "
                "range — for questions about meetings, classes, or 'what's on my calendar', as "
                "opposed to deadlines/announcements extracted from mail/Discord (use "
                "search_timeline/query_timeline for those). Always pass time_min/time_max for "
                "date-scoped questions like 'hôm nay' (today) or 'tuần này' (this week) — "
                "resolve the actual date yourself from today's date (given in the system "
                "prompt) before calling; this tool does not interpret relative dates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["google", "outlook"], "description": "Which calendar to check."},
                    "time_min": {"type": "string", "description": "ISO 8601 start of range, e.g. 2026-07-31T00:00:00+07:00."},
                    "time_max": {"type": "string", "description": "ISO 8601 end of range, e.g. 2026-07-31T23:59:59+07:00."},
                    "query": {"type": "string", "description": "Optional text filter."},
                },
                "required": ["platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_search",
            "description": (
                "LIVE search of the student's actual Gmail (not the ingested/extracted "
                "timeline) using Gmail search syntax, e.g. 'is:unread newer_than:7d', "
                "'from:...'. Use for mail outside what's already been ingested, or when the "
                "student wants to search their inbox directly rather than ask about known "
                "deadlines. Returns thread_id values for gmail_read_thread."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search syntax."},
                    "max_results": {"type": "integer", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_read_thread",
            "description": "Read the full content of one Gmail thread found via gmail_search.",
            "parameters": {
                "type": "object",
                "properties": {"thread_id": {"type": "string"}},
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "outlook_mail_search",
            "description": (
                "LIVE search of the student's actual Outlook mail (not the ingested/extracted "
                "timeline) using KQL (e.g. 'subject:\"deadline\"', 'from:...'), or lists recent "
                "messages across all folders if query is empty."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "outlook_mail_read",
            "description": "Read the full content of one Outlook message by message_id, from outlook_mail_search.",
            "parameters": {
                "type": "object",
                "properties": {"message_id": {"type": "string"}},
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_list_guilds",
            "description": (
                "List every Discord server (guild) the bot has been invited into and can "
                "currently see. Call this first if the student asks about 'the Discord server' "
                "or a server by name and you don't already know its guild_id, or there's more "
                "than one and you need to disambiguate."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_server_info",
            "description": (
                "Details (name, member count, channel count, owner, created date) of a Discord "
                "server the bot has been invited into. Leave guild_id empty if the bot is only "
                "in one server; otherwise call discord_list_guilds first."
            ),
            "parameters": {
                "type": "object",
                "properties": {"guild_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_list_channels",
            "description": (
                "List every channel in a Discord server, grouped by category. Use when the "
                "student asks broadly about a SERVER ('có gì mới trên X') rather than naming one "
                "specific channel — pick the relevant channel(s) from this list, then call "
                "discord_read_messages on each, instead of guessing a channel name for "
                "discord_find_channel."
            ),
            "parameters": {
                "type": "object",
                "properties": {"guild_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_find_channel",
            "description": "Find a Discord channel's ID by (partial) name. Needed before discord_read_messages, unless discord_list_channels already gave you the id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "guild_id": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_read_messages",
            "description": (
                "LIVE read of recent message history from a Discord channel (not the ingested/"
                "extracted timeline) — use for content in a channel/guild that hasn't been "
                "ingested yet, or when the student wants to see actual recent chat rather than "
                "an extracted deadline. Get channel_id from discord_find_channel or "
                "discord_list_channels first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "count": {"type": "integer", "default": 50},
                },
                "required": ["channel_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Add a real event to the student's Google Calendar — the only WRITE tool "
                "available. Two-step, spanning two separate chat turns: call with confirmed "
                "omitted/false first, which does NOT create anything — it only checks the "
                "details are valid and returns a needs_confirmation result. Restate exactly "
                "what will be created (title, date/time, any meet link) in your response_text "
                "as a plain question and STOP — do not call this tool again in the same turn. "
                "Only on a LATER turn, after the student's own next message clearly says yes/"
                "confirms (not just continues the conversation), call it again with confirmed=true "
                "using the exact same details. Never set confirmed=true on the first call, and "
                "never infer confirmation from anything other than an explicit yes in the "
                "student's own following message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start": {"type": "string", "description": "ISO 8601 start, e.g. 2026-08-05T15:00:00+07:00."},
                    "end": {"type": "string", "description": "ISO 8601 end."},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "timezone": {"type": "string", "description": "e.g. Asia/Ho_Chi_Minh."},
                    "add_meet_link": {
                        "type": "boolean",
                        "description": "Attach a real, freshly-generated Google Meet link. Never write a meet.google.com URL yourself — it won't be a working meeting.",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be true to actually create the event — only set true on a later turn, after the student explicitly confirmed.",
                        "default": False,
                    },
                },
                "required": ["summary", "start", "end"],
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


# Tools that map straight onto an existing TOOL_FUNCTIONS entry of the same
# name, with no ExtractedItem/timeline shape to reconcile — their result is
# just handed back to the LLM as-is (see execute_rag_tool). Deliberately
# read-only: calendar_create_event (also in TOOL_FUNCTIONS) is NOT here —
# it writes a real calendar event, and its own docstring requires
# confirmed=True only after the user has explicitly confirmed via a
# clarify/response_type=yes_no round-trip. rag_chatbot_node's tool loop has
# no pause/resume (interrupt) mechanism the way hitl_escalation does for
# ingestion, so it can't currently honor that confirm step — wiring the
# write tool in without it would let one ambiguous chat message create a
# real event on the student's calendar with no confirmation UI in between.
_PASSTHROUGH_TOOLS = {
    "gmail_search",
    "gmail_read_thread",
    "outlook_mail_search",
    "outlook_mail_read",
    "discord_find_channel",
    "discord_read_messages",
    "discord_list_guilds",
    "discord_server_info",
    "discord_list_channels",
}


def execute_rag_tool(name: str, args: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Run one tool call. Returns (text to feed back to the LLM, raw items
    for the caller's citation bookkeeping). Never raises — a broken tool
    call becomes an error string the LLM sees and can react to, same as the
    old chat.py agent loop's execute_tool_call."""
    try:
        if name == "list_calendar_events":
            from tools import TOOL_FUNCTIONS

            platform = args.get("platform", "google")
            func = TOOL_FUNCTIONS["calendar_list_events" if platform == "google" else "outlook_calendar_list_events"]
            kwargs: dict[str, Any] = {}
            if args.get("time_min"):
                kwargs["time_min"] = args["time_min"]
            if args.get("time_max"):
                kwargs["time_max"] = args["time_max"]
            if args.get("query"):
                kwargs["query"] = args["query"]
            result = func(**kwargs)
            # Not a timeline_items citation — a real calendar event has no
            # ExtractedItem id/source_platform to dedupe/cite by that shape,
            # so this bypasses _compact/items_to_citations entirely and just
            # hands the tool's own text back to the LLM.
            return json.dumps(result, ensure_ascii=False, default=str), []
        if name in _PASSTHROUGH_TOOLS:
            from tools import TOOL_FUNCTIONS

            result = TOOL_FUNCTIONS[name](**args)
            return json.dumps(result, ensure_ascii=False, default=str), []
        if name == "create_calendar_event":
            from tools import TOOL_FUNCTIONS

            result = TOOL_FUNCTIONS["calendar_create_event"](
                summary=args.get("summary", ""),
                start=args.get("start", ""),
                end=args.get("end", ""),
                description=args.get("description", ""),
                location=args.get("location", ""),
                timezone=args.get("timezone", ""),
                add_meet_link=bool(args.get("add_meet_link", False)),
                confirmed=bool(args.get("confirmed", False)),
            )
            return json.dumps(result, ensure_ascii=False, default=str), []
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
