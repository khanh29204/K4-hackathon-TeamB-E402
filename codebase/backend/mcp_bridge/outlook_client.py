"""HTTP client for the Outlook bridge (codebase/mcp/outlook_bridge), a small
streamable-HTTP MCP server that runs on a machine with real Docker access and
holds one outlook-local-mcp container open (see that package for why).

Railway (where this backend runs) has no Docker daemon, so unlike the old
version of this module — which used to spawn `docker run` itself and hold a
stdio session open for the whole process — persistence is now the bridge's
problem, not this backend's. Every call here is a fresh, stateless HTTP
request, the same pattern http_mcp_client.py already uses for
discord_mcp/gmail_mcp/google_calendar_mcp; the only difference is the
Authorization header, since the bridge is reachable from the public internet
via a Cloudflare Tunnel rather than only from inside one Railway container.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

OUTLOOK_MCP_URL = os.environ.get("OUTLOOK_MCP_URL", "http://localhost:8088/mcp")
OUTLOOK_MCP_AUTH_TOKEN = os.environ.get("OUTLOOK_MCP_AUTH_TOKEN", "")


@asynccontextmanager
async def connect() -> AsyncIterator[ClientSession]:
    headers = {"Authorization": f"Bearer {OUTLOOK_MCP_AUTH_TOKEN}"} if OUTLOOK_MCP_AUTH_TOKEN else None
    async with streamablehttp_client(OUTLOOK_MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_tool_text(name: str, arguments: dict[str, Any]) -> str:
    async with connect() as session:
        # The bridge's tools (codebase/mcp/outlook_bridge/server.py) each take
        # a single `arguments: dict` parameter — a schema-agnostic passthrough
        # to outlook-local-mcp's own domain tools — so the call's real payload
        # nests one level deeper than a typical MCP tool call.
        result = await session.call_tool(name, {"arguments": arguments})
        text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
        if result.isError:
            raise RuntimeError(f"Outlook MCP tool '{name}' returned an error: {text}")
        return text
