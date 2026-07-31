"""Bridge for Gmail (calls local FastMCP server with direct Gmail REST API fallback)."""

from __future__ import annotations

import base64
import html
import logging
import os
import re
from typing import Any

import httpx
import google_connection
from mcp_bridge.http_mcp_client import call_tool_text

GMAIL_MCP_URL = os.environ.get("GMAIL_MCP_URL", "http://localhost:8087/mcp")

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def _html_to_text(raw_html: str) -> str:
    text = _TAG_RE.sub("\n", raw_html)
    text = html.unescape(text)
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _extract_body(payload: dict[str, Any]) -> str:
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime == "text/plain" and body.get("data"):
        return _decode_part(body["data"])
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    if mime == "text/html" and body.get("data"):
        return _html_to_text(_decode_part(body["data"]))
    return ""


def _header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


async def _fallback_search_threads(query: str, max_results: int) -> str:
    creds = google_connection.load_credentials()
    if not creds or not creds.token:
        raise RuntimeError("Chưa kết nối Google. Vui lòng đăng nhập Google trước.")

    headers = {"Authorization": f"Bearer {creds.token}"}
    params: dict[str, Any] = {"maxResults": max_results}
    if query:
        params["q"] = query

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/threads",
            headers=headers,
            params=params,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Gmail API error ({resp.status_code}): {resp.text}")

        threads = resp.json().get("threads", [])
        if not threads:
            return "Không tìm thấy email nào phù hợp."

        summaries = []
        for t in threads:
            t_resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{t['id']}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            if t_resp.status_code == 200:
                t_data = t_resp.json()
                msgs = t_data.get("messages", [])
                first_msg = msgs[0] if msgs else {}
                h_list = first_msg.get("payload", {}).get("headers", [])
                subj = _header(h_list, "Subject") or "(Không có tiêu đề)"
                sender = _header(h_list, "From") or "Không rõ"
                date = _header(h_list, "Date") or ""
                snippet = first_msg.get("snippet", "")
                summaries.append(f"• Thread ID: {t['id']}\n  Từ: {sender}\n  Tiêu đề: {subj}\n  Ngày: {date}\n  Xem trước: {snippet}")

        return "\n\n".join(summaries)


async def _fallback_get_thread(thread_id: str) -> str:
    creds = google_connection.load_credentials()
    if not creds or not creds.token:
        raise RuntimeError("Chưa kết nối Google. Vui lòng đăng nhập Google trước.")

    headers = {"Authorization": f"Bearer {creds.token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
            headers=headers,
            params={"format": "full"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Gmail API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        msgs = data.get("messages", [])
        out = []
        for msg in msgs:
            h_list = msg.get("payload", {}).get("headers", [])
            sender = _header(h_list, "From")
            date = _header(h_list, "Date")
            body = _extract_body(msg.get("payload", {}))
            out.append(f"--- Tin nhắn từ {sender} ({date}) ---\n{body}")

        return "\n\n".join(out)


async def call_gmail_tool(name: str, arguments: dict[str, Any]) -> str:
    try:
        return await call_tool_text(GMAIL_MCP_URL, name, arguments)
    except Exception as exc:
        logging.warning("Gmail MCP server call failed (%s), using direct Gmail API fallback", exc)
        if name == "search_threads":
            query = arguments.get("query", "")
            max_results = int(arguments.get("max_results", 10))
            return await _fallback_search_threads(query, max_results)
        elif name == "get_thread":
            thread_id = arguments.get("thread_id", "")
            return await _fallback_get_thread(thread_id)
        raise
