from __future__ import annotations

import asyncio
from typing import Any

from mcp_bridge.gmail_client import call_gmail_tool
from tools._shared import err


def gmail_search(query: str = "", max_results: int = 10) -> dict[str, Any]:
    """Search Gmail threads. `query` uses Gmail search syntax, e.g. `is:unread newer_than:7d`."""
    try:
        args = {"query": query, "max_results": str(max_results)}
        text = asyncio.run(call_gmail_tool("search_threads", args))
        return {"tool": "gmail_search", "query": query, "text": text}
    except Exception as exc:
        return err("gmail_search", exc)
