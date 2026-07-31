"""Bridge to Google Calendar (calendarmcp.googleapis.com with fallback to Calendar REST API).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import google_connection
from mcp_bridge.http_mcp_client import call_tool_structured

GOOGLE_CALENDAR_MCP_URL = os.environ.get(
    "GOOGLE_CALENDAR_MCP_URL", "https://calendarmcp.googleapis.com/mcp/v1"
)


class CalendarNotConnectedError(RuntimeError):
    """No usable Google token — the user has not completed (or has revoked) the
    "Quản lý kết nối" > Gmail OAuth flow."""


def _auth_headers() -> dict[str, str]:
    creds = google_connection.load_credentials()
    if creds is None or not creds.token:
        raise CalendarNotConnectedError(
            "Chưa kết nối Google. Vào FE > \"Quản lý kết nối\" > Gmail để cấp quyền "
            "Google Calendar trước khi dùng các tool calendar."
        )
    return {"Authorization": f"Bearer {creds.token}"}


async def _fallback_list_events(arguments: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    calendar_id = arguments.get("calendarId") or "primary"
    params: dict[str, Any] = {}
    if "pageSize" in arguments:
        params["maxResults"] = arguments["pageSize"]
    if "orderBy" in arguments:
        params["orderBy"] = arguments["orderBy"]
        if arguments["orderBy"] == "startTime":
            params["singleEvents"] = "true"
    if "startTime" in arguments:
        params["timeMin"] = arguments["startTime"]
    if "endTime" in arguments:
        params["timeMax"] = arguments["endTime"]
    if "fullText" in arguments:
        params["q"] = arguments["fullText"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers=headers,
            params=params,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Google Calendar API error ({resp.status_code}): {resp.text}")
        data = resp.json()
        items = data.get("items", [])
        events = []
        for item in items:
            events.append({
                "id": item.get("id", ""),
                "summary": item.get("summary", ""),
                "description": item.get("description", ""),
                "location": item.get("location", ""),
                "start": item.get("start", {}),
                "end": item.get("end", {}),
                "htmlLink": item.get("htmlLink", ""),
            })
        return {"events": events}


async def _fallback_create_event(arguments: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    calendar_id = arguments.get("calendarId") or "primary"
    body = {
        "summary": arguments.get("summary", ""),
        "description": arguments.get("description", ""),
        "start": arguments.get("start", {}),
        "end": arguments.get("end", {}),
    }
    if "location" in arguments:
        body["location"] = arguments["location"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers=headers,
            json=body,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Google Calendar API error ({resp.status_code}): {resp.text}")
        return resp.json()


async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a tool on Google's Calendar MCP server, with direct REST API fallback."""
    headers = _auth_headers()
    try:
        return await call_tool_structured(GOOGLE_CALENDAR_MCP_URL, name, arguments, headers)
    except Exception as exc:
        logging.warning("Hosted Calendar MCP failed (%s), falling back to Calendar REST API", exc)
        if name == "list_events":
            return await _fallback_list_events(arguments, headers)
        elif name in ("create_event", "quick_add_event"):
            return await _fallback_create_event(arguments, headers)
        raise
