"""Persistent stdio session to outlook-local-mcp's Docker container.

Ported from the backend's old codebase/backend/mcp_bridge/outlook_client.py,
which used to run this same logic *inside* the FastAPI process. It's moved
here because Railway (where the backend now runs) has no Docker daemon
access — this module runs on a machine that actually has Docker, and
server.py exposes it over streamable-HTTP for the backend to call remotely.

Exactly ONE `docker run` container, opened lazily on first use and kept open
for the life of this process, reused by every caller — see
outlook_mcp/client.py and the original outlook_client.py docstring for why a
fresh container per call breaks Microsoft's device-code auth. If this bridge
process restarts, one fresh sign-in is needed again.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import config

# Device-code auth (first run, or whenever the cached token has expired) can
# sit waiting on the user for a while. Only the call that actually opens the
# session pays this cost; every call after that gets the normal timeout.
FIRST_CALL_TIMEOUT = timedelta(minutes=15)
DEFAULT_CALL_TIMEOUT = timedelta(seconds=60)


@asynccontextmanager
async def open_session() -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(command="docker", args=config.docker_run_args())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_tool(session: ClientSession, name: str, arguments: dict[str, Any], timeout: timedelta) -> str:
    result = await session.call_tool(name, arguments, read_timeout_seconds=timeout)
    text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
    if result.isError:
        raise RuntimeError(f"Outlook MCP tool '{name}' returned an error: {text}")
    return text


# --- Shared persistent session -------------------------------------------

_shared_lock = threading.Lock()
_shared_loop: asyncio.AbstractEventLoop | None = None
_shared_session_cm: Any = None
_shared_session: ClientSession | None = None
_session_just_opened = False


def _ensure_shared_loop() -> asyncio.AbstractEventLoop:
    global _shared_loop
    with _shared_lock:
        if _shared_loop is None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, daemon=True).start()
            _shared_loop = loop
        return _shared_loop


async def _open_shared_session() -> ClientSession:
    global _shared_session_cm, _shared_session, _session_just_opened
    cm = open_session()
    session = await cm.__aenter__()
    _shared_session_cm = cm
    _shared_session = session
    _session_just_opened = True
    return session


async def _close_shared_session() -> None:
    global _shared_session_cm, _shared_session
    cm, _shared_session_cm = _shared_session_cm, None
    _shared_session = None
    if cm is not None:
        try:
            await cm.__aexit__(None, None, None)
        except Exception:
            pass


async def _get_shared_session() -> ClientSession:
    if _shared_session is None:
        await _open_shared_session()
    return _shared_session


async def _run_on_shared_session(coro_fn: Any) -> Any:
    session = await _get_shared_session()
    return await coro_fn(session)


async def call_tool_text(name: str, arguments: dict[str, Any]) -> str:
    """Call a domain tool ("mail", "calendar", "system", "account") using the
    one persistent shared session, opening it if needed. Retries once
    against a freshly (re)opened session if the call fails."""
    global _session_just_opened

    async def attempt(session: ClientSession) -> str:
        global _session_just_opened
        timeout = FIRST_CALL_TIMEOUT if _session_just_opened else DEFAULT_CALL_TIMEOUT
        _session_just_opened = False
        return await call_tool(session, name, arguments, timeout)

    loop = _ensure_shared_loop()

    async def runner() -> str:
        return await _run_on_shared_session(attempt)

    try:
        future = asyncio.run_coroutine_threadsafe(runner(), loop)
        return await asyncio.wrap_future(future)
    except Exception:
        async def reset(_session: ClientSession) -> None:
            await _close_shared_session()

        reset_future = asyncio.run_coroutine_threadsafe(_run_on_shared_session(reset), loop)
        await asyncio.wrap_future(reset_future)

        retry_future = asyncio.run_coroutine_threadsafe(runner(), loop)
        return await asyncio.wrap_future(retry_future)
