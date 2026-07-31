"""Entrypoint: run the Outlook bridge as a streamable-HTTP MCP server,
protected by a static bearer-token check, since (unlike discord_mcp/gmail_mcp/
google_calendar_mcp) this one is reachable from the public internet via a
Cloudflare Tunnel rather than only from inside one Railway container.
"""

import uvicorn
from starlette.responses import JSONResponse

from . import config
from .server import mcp


class BearerAuthMiddleware:
    """Raw ASGI middleware (not starlette.middleware.base.BaseHTTPMiddleware,
    which buffers the response and can break the streamable-HTTP transport's
    SSE-style streaming) — checks the Authorization header before letting
    HTTP requests through; lifespan/websocket scopes pass through untouched
    so FastMCP's own session-manager startup still runs."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = f"Bearer {token}"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        if headers.get(b"authorization", b"").decode() != self.token:
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def main() -> None:
    app = BearerAuthMiddleware(mcp.streamable_http_app(), config.AUTH_TOKEN)
    url = f"http://{config.BRIDGE_HOST}:{config.BRIDGE_PORT}{mcp.settings.streamable_http_path}"
    print(f"Starting Outlook bridge (streamable-http, auth required) at {url}")
    uvicorn.run(app, host=config.BRIDGE_HOST, port=config.BRIDGE_PORT)


if __name__ == "__main__":
    main()
