"""HTTP entrypoint for the StudyPulse agent, for the Vite/React frontend in
codebase/FE. /api/v1/chat runs the studypulse/ LangGraph pipeline
(compile_graph().invoke, see studypulse/graph.py) — NOT agent.run_model_tool_loop
+ tools.TOOL_FUNCTIONS, which chat.py (the CLI) still uses; see the
mail-rag-design migration artifact for why these two now diverge.
TOOL_FUNCTIONS stays imported here only for calendar_create_event, called
directly from confirm_calendar() outside any chat loop. See specs/UI.md for
the response envelope /api/v1/chat follows.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel

import discord_connection
import google_connection
import outlook_connection
from env_loader import load_backend_env
from studypulse import hitl
from studypulse.graph import get_compiled_graph
from studypulse.mail_ingest import trigger_ingestion_async
from studypulse.storage import get_db
from timeline_view import to_card
from tools import TOOL_FUNCTIONS

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
load_backend_env(ROOT)

# Cache-busting/debug marker for the FE — hashed from what actually drives
# chat behavior now (studypulse's prompt), not artifacts/system_prompt.md
# (that file only matters to chat.py's separate tool-calling loop).
_ARTIFACT_VERSION = hashlib.sha256(
    (ROOT / "studypulse" / "system_prompt.py").read_bytes()
).hexdigest()[:12]

app = FastAPI(title="StudyPulse agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def envelope(data: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "error": error, "meta": {"request_id": uuid.uuid4().hex, "timestamp": now_iso()}}


def error_response(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=envelope(error={"code": code, "message": message, "details": {}}))


class ChatRequest(BaseModel):
    user_query: str
    conversation_id: str | None = None


@app.post("/api/v1/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """SSE streaming endpoint for /api/v1/chat. Streams response text tokens/chunks
    to the frontend in real-time for an enhanced UI experience."""
    import json
    import time

    try:
        google_status = google_connection.get_status()
    except Exception:
        google_status = {"connected": False}

    if not google_status.get("connected"):
        raise error_response(
            401,
            "UNAUTHORIZED",
            "Bạn chưa đăng nhập Google. Vui lòng bấm 'Đăng nhập với Google' ở góc trên bên phải để bắt đầu sử dụng trợ lý StudyPulse AI.",
        )

    conversation_id = request.conversation_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": conversation_id}}

    def sse_event_generator():
        yield f"data: {json.dumps({'type': 'status', 'message': 'Đang tìm kiếm và xử lý...'}, ensure_ascii=False)}\n\n"

        try:
            final_state = get_compiled_graph().invoke(
                {"flow_type": "chat", "user_query": request.user_query, "raw_payload": {}},
                config=config,
            )
        except Exception as exc:
            err_data = {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
            yield f"data: {json.dumps(err_data, ensure_ascii=False)}\n\n"
            return

        assistant_text = final_state.get("final_response", "")
        chat_resp = final_state.get("chat_response") or {}
        blocked = bool(final_state.get("guardrail_blocked"))

        # Stream text in small chunks for live typing effect
        chunk_size = 4
        words = assistant_text.split(" ")
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            event_data = {"type": "delta", "text": chunk}
            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
            time.sleep(0.02)

        data = {
            "query_id": uuid.uuid4().hex,
            "conversation_id": conversation_id,
            "timestamp": now_iso(),
            "response_text": assistant_text,
            "sources_cited": chat_resp.get("sources_cited", []),
            "calendar_events": [],
            "timeline_items_referenced": chat_resp.get("timeline_items_referenced", []),
            "requires_clarification": bool(chat_resp.get("requires_clarification", False)),
            "suggested_actions": chat_resp.get("suggested_actions", []),
            "status": "blocked" if blocked else "answered",
            "artifact_version": _ARTIFACT_VERSION,
        }
        done_event = {"type": "done", "data": data}
        yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")


class PatchTimelineRequest(BaseModel):
    date: str | None = None
    time: str | None = None
    due_date_iso: str | None = None
    due_time_iso: str | None = None


class FeedbackRequest(BaseModel):
    feedback_type: str = "incorrect"
    note: str | None = None


class CalendarConfirmRequest(BaseModel):
    timezone: str | None = None


class DiscordDisconnectRequest(BaseModel):
    guild_id: str


class HitlApproveRequest(BaseModel):
    edits: dict[str, Any] | None = None


FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5190")


@app.post("/api/v1/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    """Runs one turn through the studypulse graph's chat flow
    (ingestion -> guardrail -> language_detect -> intent_router ->
    rag_chatbot -> response_formatter). conversation_id doubles as the
    LangGraph thread_id: the compiled graph's checkpointer (see
    studypulse/graph.py get_checkpointer) restores that thread's
    chat_history/user_profile automatically, so only this turn's
    user_query needs to be passed in — no in-memory history dict here
    anymore.

    Known gap vs. the old tool-calling loop: rag_chatbot_node only answers
    from what's already been ingested (mail via studypulse/mail_ingest.py,
    triggered on connect) plus FAISS — there's no live tool call mid-chat,
    so calendar_events is always empty here (Discord/calendar ingestion is
    a later migration phase) and requires_clarification only reflects the
    guardrail, not a clarify-style follow-up question (no graph equivalent
    yet). See the mail-rag-design migration artifact, section 3c.
    """

    try:
        google_status = google_connection.get_status()
    except Exception:
        google_status = {"connected": False}

    if not google_status.get("connected"):
        raise error_response(
            401,
            "UNAUTHORIZED",
            "Bạn chưa đăng nhập Google. Vui lòng bấm 'Đăng nhập với Google' ở góc trên bên phải để bắt đầu sử dụng trợ lý StudyPulse AI.",
        )

    conversation_id = request.conversation_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": conversation_id}}

    try:
        final_state = get_compiled_graph().invoke(
            {"flow_type": "chat", "user_query": request.user_query, "raw_payload": {}},
            config=config,
        )
    except Exception as exc:
        raise error_response(502, "PROVIDER_ERROR", f"{type(exc).__name__}: {exc}") from exc

    assistant_text = final_state.get("final_response", "")
    chat_resp = final_state.get("chat_response") or {}
    blocked = bool(final_state.get("guardrail_blocked"))

    data = {
        "query_id": uuid.uuid4().hex,
        "conversation_id": conversation_id,
        "timestamp": now_iso(),
        "response_text": assistant_text,
        "sources_cited": chat_resp.get("sources_cited", []),
        "calendar_events": [],
        "timeline_items_referenced": chat_resp.get("timeline_items_referenced", []),
        "requires_clarification": bool(chat_resp.get("requires_clarification", False)),
        "suggested_actions": chat_resp.get("suggested_actions", []),
        "status": "blocked" if blocked else "answered",
        "artifact_version": _ARTIFACT_VERSION,
    }
    return envelope(data=data)


@app.get("/api/v1/timeline")
def get_timeline() -> dict[str, Any]:
    """Reads studypulse's SQLite (studypulse/storage.py), filtered by user_id for multi-tenant support."""
    try:
        google_status = google_connection.get_status()
        user_email = google_status.get("email")
    except Exception:
        user_email = None
    items = [to_card(item) for item in get_db().get_all_timeline(user_id=user_email)]
    return envelope(data={"items": items, "total": len(items)})


@app.patch("/api/v1/timeline/{item_id}")
def patch_timeline(item_id: str, request: PatchTimelineRequest) -> dict[str, Any]:
    patch = {k: v for k, v in request.model_dump().items() if v is not None}
    item = get_db().update_timeline_item(item_id, patch)
    if item is None:
        raise error_response(404, "NOT_FOUND", f"No timeline item with id {item_id}")
    return envelope(data=to_card(item))


@app.post("/api/v1/timeline/{item_id}/feedback")
def flag_timeline(item_id: str, request: FeedbackRequest) -> dict[str, Any]:
    removed = get_db().delete_timeline_item(item_id)
    if not removed:
        raise error_response(404, "NOT_FOUND", f"No timeline item with id {item_id}")
    return envelope(data={"status": "queued_for_review", "item_id": item_id})


@app.post("/api/v1/timeline/{item_id}/calendar")
def confirm_calendar(item_id: str, request: CalendarConfirmRequest) -> dict[str, Any]:
    item = get_db().get_timeline_item(item_id)
    if item is None:
        raise error_response(404, "NOT_FOUND", f"No timeline item with id {item_id}")
    card = to_card(item)

    due_date_iso = card["due_date_iso"]
    if not due_date_iso:
        raise error_response(
            422,
            "MISSING_DATE",
            "Mục này chưa có ngày cụ thể được xác nhận từ nguồn — không thể thêm vào Calendar. "
            "Hãy chỉnh sửa lại thời gian trước, hoặc kiểm tra nguồn gốc.",
        )

    due_time_iso = card["due_time_iso"]
    start = f"{due_date_iso}T{due_time_iso}:00" if due_time_iso else due_date_iso
    kwargs: dict[str, Any] = {
        "summary": card["title"],
        "start": start,
        "end": start,
        "description": card.get("detail", ""),
        "confirmed": True,
    }
    if due_time_iso:
        kwargs["timezone"] = request.timezone or "Asia/Ho_Chi_Minh"
    elif request.timezone:
        kwargs["timezone"] = request.timezone

    result = TOOL_FUNCTIONS["calendar_create_event"](**kwargs)
    if "error" in result:
        raise error_response(502, "CALENDAR_ERROR", result.get("message", "calendar_create_event failed"))

    get_db().update_timeline_item(item_id, {"verified": True})
    return envelope(data={"status": result.get("status", "created"), "detail": result.get("text", "")})


@app.get("/api/v1/hitl")
def list_hitl() -> dict[str, Any]:
    """Items the graph paused on at hitl_escalation (confidence < 0.85 —
    see studypulse/graph.py's route_by_confidence), across every ingestion
    thread. Raw ExtractedItem shape (+ thread_id), not the FE's EventCard
    shape from timeline_view.to_card — a review queue needs fields
    (validation_issues, confidence_score, raw_snippet) that shape strips
    out, and no FE component consumes this yet to hold a contract to."""
    items = hitl.list_pending()
    return envelope(data={"items": items, "total": len(items)})


@app.post("/api/v1/hitl/{thread_id}/{item_id}/approve")
def approve_hitl(thread_id: str, item_id: str, request: HitlApproveRequest) -> dict[str, Any]:
    """Saves the item to SQLite/FAISS despite its low confidence — bypasses
    dashboard_sync_node, which this item's thread never reaches (hitl_escalation
    has no edge back to it, see graph.py). `edits` lets a reviewer fix
    whatever extraction couldn't confirm (e.g. due_date) before saving."""
    item = hitl.approve(thread_id, item_id, edits=request.edits)
    if item is None:
        raise error_response(404, "NOT_FOUND", f"No pending HITL item {item_id} on thread {thread_id}")
    return envelope(data=item)


@app.post("/api/v1/hitl/{thread_id}/{item_id}/reject")
def reject_hitl(thread_id: str, item_id: str) -> dict[str, Any]:
    """Discards the item — never saved."""
    ok = hitl.reject(thread_id, item_id)
    if not ok:
        raise error_response(404, "NOT_FOUND", f"No pending HITL item {item_id} on thread {thread_id}")
    return envelope(data={"status": "rejected", "thread_id": thread_id, "item_id": item_id})


@app.get("/api/v1/connections")
def get_connections() -> dict[str, Any]:
    """Status of the connections the backend actually knows how to manage.
    One Google connection (shared by Gmail + Calendar), one Discord
    connection (shared bot, one server), and one Outlook connection (its own
    account registry inside outlook-local-mcp's Docker container/volume —
    see outlook_connection.py); other platforms in the FE's connection list
    remain client-side only for now."""
    try:
        google_status = google_connection.get_status()
    except google_connection.GoogleConnectionError:
        google_status = {"connected": False, "email": None, "scopes": []}
    discord_status = discord_connection.get_status()
    outlook_status = outlook_connection.get_status()
    return envelope(data={"google": google_status, "discord": discord_status, "outlook": outlook_status})


@app.get("/api/v1/connections/google/start")
def start_google_connection() -> dict[str, Any]:
    try:
        auth_url = google_connection.get_authorization_url()
    except google_connection.GoogleConnectionError as exc:
        raise error_response(400, "GOOGLE_OAUTH_NOT_CONFIGURED", str(exc)) from exc
    return envelope(data={"auth_url": auth_url})


@app.get("/api/v1/connections/google/callback")
def google_connection_callback(code: str | None = None, error: str | None = None) -> RedirectResponse:
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?google_connected=0&reason={error}")
    if not code:
        return RedirectResponse(f"{FRONTEND_URL}/?google_connected=0&reason=missing_code")
    try:
        google_connection.exchange_code(code)
    except Exception:
        logging.exception("Google OAuth token exchange failed")
        return RedirectResponse(f"{FRONTEND_URL}/?google_connected=0&reason=exchange_failed")
    # Fire-and-forget: sync + classify recent unread mail now that we have a
    # token, rather than waiting on a timer or the first chat query — see
    # studypulse/mail_ingest.py.
    trigger_ingestion_async("gmail")
    return RedirectResponse(f"{FRONTEND_URL}/?google_connected=1")


@app.post("/api/v1/connections/google/disconnect")
def disconnect_google_connection() -> dict[str, Any]:
    google_connection.disconnect()
    return envelope(data={"connected": False})


@app.get("/api/v1/connections/discord/start")
def start_discord_connection() -> dict[str, Any]:
    """Returns the bot invite URL. Completing it is a manual, one-time action
    by whoever administers the target Discord server — Discord requires
    "Manage Server" on the inviting account, which this backend cannot do on
    anyone's behalf."""
    invite_url = discord_connection.get_invite_url()
    if not invite_url:
        raise error_response(
            400,
            "DISCORD_CLIENT_ID_NOT_SET",
            "Thiếu DISCORD_CLIENT_ID trong codebase/mcp/.env — lấy Application ID trong Discord "
            "Developer Portal (tab General Information).",
        )
    return envelope(data={"invite_url": invite_url})


@app.post("/api/v1/connections/discord/disconnect")
def disconnect_discord_connection(request: DiscordDisconnectRequest) -> dict[str, Any]:
    try:
        discord_connection.disconnect(request.guild_id)
    except ValueError as exc:
        raise error_response(400, "GUILD_ID_REQUIRED", str(exc)) from exc
    except Exception as exc:
        raise error_response(502, "DISCORD_DISCONNECT_FAILED", str(exc)) from exc
    return envelope(data={"guild_id": request.guild_id})


@app.post("/api/v1/connections/outlook/start")
def start_outlook_connection() -> dict[str, Any]:
    """Trigger (or check on) Outlook device-code sign-in — see
    outlook_connection.start_connect() for why this can't just be a fresh
    tool call per click. Returns quickly with either 'connected' (a cached
    token already worked) or 'pending' plus the device-code text to show the
    user; the FE then polls /connections/outlook/connect-status."""
    return envelope(data=outlook_connection.start_connect())


@app.get("/api/v1/connections/outlook/connect-status")
def get_outlook_connect_status() -> dict[str, Any]:
    return envelope(data=outlook_connection.get_connect_status())


@app.post("/api/v1/connections/outlook/disconnect")
def disconnect_outlook_connection() -> dict[str, Any]:
    try:
        outlook_connection.disconnect()
    except Exception as exc:
        raise error_response(502, "OUTLOOK_DISCONNECT_FAILED", str(exc)) from exc
    return envelope(data={"connected": False})
