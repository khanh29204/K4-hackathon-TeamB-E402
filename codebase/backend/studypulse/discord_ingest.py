"""Discord ingestion: fetch full channel history (paginated) and chunk it
into extraction-sized pieces, then feed each chunk through the same
studypulse ingestion flow mail_ingest.py uses.

Deliberately not a prefilter-then-fetch shape like mail_ingest.py: Discord
has no per-user "unread" state reachable via a bot (bots don't get read
receipts), so there's no cheap signal to filter on before spending an LLM
call the way mail's isRead/date-window prefilter works. Per explicit
steer: fetch everything in a channel, chunk it, ingest every chunk.

Trigger: there's no OAuth-callback-style "just connected" event for Discord
(see discord_connection.py's docstring — the bot joining a guild isn't
something this backend is told about, only something it can poll for), so
unlike mail's connection-triggered hooks, this is triggered from
discord_connection.get_status()'s poll loop noticing a guild id it hasn't
seen before — see that module for the actual trigger wiring.

Opt-out, not opt-in: every text/announcement channel in a newly-seen guild
gets ingested by default (matches the "everything" steer), except channel
or guild ids listed in DISCORD_INGEST_CHANNEL_DENYLIST /
DISCORD_INGEST_GUILD_DENYLIST (comma-separated snowflake ids, see
.env.example) — an escape hatch for channels that shouldn't feed the
assistant, not a switch to opt in per channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any

from mcp_bridge.http_mcp_client import call_tool_text
from tools._shared import DISCORD_MCP_URL

from . import ingest_status
from .graph import get_compiled_graph
from .state import SourcePlatform

logger = logging.getLogger(__name__)

DEFAULT_MAX_MESSAGES_PER_CHANNEL = 500
DEFAULT_CHUNK_CHARS = 6000
_PAGE_SIZE = 100  # Discord API max per read_messages call, see discord_mcp/tools.py


def _denylisted_ids(env_var: str) -> set[str]:
    """Comma-separated Discord snowflake ids from an env var — opt-out for
    the "ingest everything" default (per steer: fetch-all-and-chunk, not a
    per-message prefilter like mail). Empty by default: nothing excluded
    unless explicitly configured. See .env.example."""
    raw = os.environ.get(env_var, "")
    return {part.strip() for part in raw.split(",") if part.strip()}


# ═══════════════════════════════════════════════════════════════════════════
# FETCH — paginate a channel's full history, oldest-first
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_page(channel_id: str, before: str | None) -> list[dict[str, Any]]:
    args: dict[str, Any] = {"channel_id": channel_id, "count": str(_PAGE_SIZE), "output": "json"}
    if before:
        args["before"] = before
    text = asyncio.run(call_tool_text(DISCORD_MCP_URL, "read_messages", args))
    return json.loads(text)


def fetch_channel_messages(
    channel_id: str,
    max_messages: int = DEFAULT_MAX_MESSAGES_PER_CHANNEL,
) -> list[dict[str, Any]]:
    """Up to max_messages from one channel, oldest-first, skipping bot
    messages and empty (attachment-only) content. Discord's history() is
    newest-first and read_messages caps at 100/call, so this pages
    backwards via `before` until max_messages or the channel start."""
    messages: list[dict[str, Any]] = []
    before: str | None = None
    while len(messages) < max_messages:
        page = _fetch_page(channel_id, before)
        if not page:
            break
        messages.extend(page)
        before = page[-1]["id"]
        if len(page) < _PAGE_SIZE:
            break
    messages = messages[:max_messages]
    messages.reverse()
    return [m for m in messages if not m.get("is_bot") and m.get("content")]


# ═══════════════════════════════════════════════════════════════════════════
# CHUNK — pack messages into extraction-sized pieces on message boundaries
# ═══════════════════════════════════════════════════════════════════════════

def chunk_messages(messages: list[dict[str, Any]], max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Greedily fills each chunk up to max_chars, never splitting a single
    message across two chunks (a lone message longer than max_chars gets
    its own oversized chunk rather than being cut mid-content)."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for m in messages:
        line = f"[{m.get('author', '?')} @ {m.get('created_at', '')}] {m.get('content', '')}"
        if current and current_len + len(line) > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


# ═══════════════════════════════════════════════════════════════════════════
# INGEST
# ═══════════════════════════════════════════════════════════════════════════

def _ingest_chunk(channel_id: str, chunk_index: int, chunk_text: str, *, guild_id: str = "") -> dict[str, Any]:
    raw_payload = {
        "source_platform": SourcePlatform.DISCORD.value,
        "message_id": f"{channel_id}:chunk-{chunk_index}",
        # Channel-level, not message-level — a chunk merges several
        # messages (see chunk_messages), so there's no single message id
        # left to link to by the time extraction sees it. guild_id is
        # required for Discord's own URL scheme to resolve the channel at
        # all; omitted (empty link) when the caller doesn't have it.
        "source_url": f"https://discord.com/channels/{guild_id}/{channel_id}" if guild_id else "",
        "body": chunk_text,
        "channel_id": channel_id,
    }
    state = {"flow_type": "ingestion", "raw_payload": raw_payload}
    config = {"configurable": {"thread_id": f"ingest_discord_{channel_id}_{chunk_index}"}}
    return get_compiled_graph().invoke(state, config=config)


def ingest_channel(channel_id: str, *, guild_id: str = "", max_messages: int = DEFAULT_MAX_MESSAGES_PER_CHANNEL) -> dict[str, Any]:
    """Fetch -> chunk -> ingest for one channel. Returns counts, not raw
    state, matching mail_ingest.ingest_new_mail's shape."""
    messages = fetch_channel_messages(channel_id, max_messages=max_messages)
    chunks = chunk_messages(messages)
    ingested = 0
    errors = 0
    for i, chunk in enumerate(chunks):
        try:
            _ingest_chunk(channel_id, i, chunk, guild_id=guild_id)
            ingested += 1
        except Exception:
            logger.exception("Failed to ingest Discord channel %s chunk %d", channel_id, i)
            errors += 1

    result = {
        "channel_id": channel_id,
        "messages": len(messages),
        "chunks": len(chunks),
        "ingested": ingested,
        "errors": errors,
    }
    logger.info("Discord channel ingestion complete: %s", result)
    return result


def _list_text_channels(guild_id: str) -> list[dict[str, Any]]:
    text = asyncio.run(call_tool_text(DISCORD_MCP_URL, "list_channels", {"guild_id": guild_id, "output": "json"}))
    channels = json.loads(text)
    denied = _denylisted_ids("DISCORD_INGEST_CHANNEL_DENYLIST")
    return [c for c in channels if c.get("type") in ("text", "news") and c.get("id") not in denied]


def ingest_guild(guild_id: str, **kwargs: Any) -> dict[str, Any]:
    """Every text/announcement channel in one guild — "get all content and
    chunk it," per steer — except channels/guilds explicitly opted out via
    DISCORD_INGEST_CHANNEL_DENYLIST / DISCORD_INGEST_GUILD_DENYLIST (see
    .env.example). Ingest-everything is still the default; this is the
    escape hatch, not a switch to opt-in per channel."""
    if guild_id in _denylisted_ids("DISCORD_INGEST_GUILD_DENYLIST"):
        logger.info("Skipping ingestion for denylisted guild %s", guild_id)
        return {"guild_id": guild_id, "channels": 0, "results": [], "skipped": "guild_denylisted"}

    channels = _list_text_channels(guild_id)
    results = []
    for c in channels:
        try:
            results.append(ingest_channel(c["id"], guild_id=guild_id, **kwargs))
        except Exception as exc:
            # One channel the bot can't actually read (e.g. missing "Read
            # Message History" in that specific channel's permission
            # overrides, even though list_channels/the guild-level invite
            # scope let it see the channel exists) used to abort every other
            # channel in the guild too, since this loop used to be a bare
            # list comprehension. Isolate it instead — same shape
            # ingest_channel already uses per-chunk. No .env denylist entry
            # needed for this case: a channel-permission 403 is expected and
            # self-resolving (skip now, retried harmlessly next sync), not a
            # channel an operator has to remember to opt out of by hand.
            logger.exception("Failed to ingest Discord channel %s (guild %s) — skipping", c["id"], guild_id)
            results.append({
                "channel_id": c["id"],
                "channel_name": c.get("name", ""),
                "messages": 0,
                "chunks": 0,
                "ingested": 0,
                "errors": 1,
                "error": str(exc)[:200],
            })
    return {"guild_id": guild_id, "channels": len(channels), "results": results}


def _ingest_guild_and_track(guild_id: str, **kwargs: Any) -> None:
    ingest_status.set_status(SourcePlatform.DISCORD.value, "running", guild_id=guild_id)
    try:
        result = ingest_guild(guild_id, **kwargs)
        ingest_status.set_status(SourcePlatform.DISCORD.value, "done", **result)
    except Exception as exc:
        logger.exception("Discord ingestion failed for guild %s", guild_id)
        ingest_status.set_status(SourcePlatform.DISCORD.value, "error", guild_id=guild_id, error=str(exc))


def trigger_guild_ingestion_async(guild_id: str, **kwargs: Any) -> None:
    """Fire-and-forget, same shape as mail_ingest.trigger_ingestion_async —
    called from discord_connection.get_status() when it notices a guild id
    it hasn't seen before. Progress is recorded in ingest_status (keyed by
    source, not per-guild — one "discord" row is enough for the FE's
    "is a sync in progress" loading state) for the FE to poll."""
    thread = threading.Thread(target=_ingest_guild_and_track, args=(guild_id,), kwargs=kwargs, daemon=True)
    thread.start()
