from typing import Any

from mcp.server.fastmcp import FastMCP

from . import config, session

mcp = FastMCP(
    "outlook-bridge",
    host=config.BRIDGE_HOST,
    port=config.BRIDGE_PORT,
)


# Thin passthroughs to outlook-local-mcp's own tools (see outlook_mcp/README.md
# for the operation verbs each domain supports) — this bridge doesn't need to
# know their schemas, it just forwards name + arguments to the one held-open
# container session.
@mcp.tool()
async def mail(arguments: dict[str, Any]) -> str:
    return await session.call_tool_text("mail", arguments)


@mcp.tool()
async def calendar(arguments: dict[str, Any]) -> str:
    return await session.call_tool_text("calendar", arguments)


@mcp.tool()
async def system(arguments: dict[str, Any]) -> str:
    return await session.call_tool_text("system", arguments)


@mcp.tool()
async def account(arguments: dict[str, Any]) -> str:
    return await session.call_tool_text("account", arguments)
