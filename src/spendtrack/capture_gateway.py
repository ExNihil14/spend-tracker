"""Capture-only ASGI edge for the remote mobile surface.

The main app stays loopback-only. Tailscale Serve must target a separate
`spendtrack capture-serve` process (default port 8767), which wraps the same
app in this edge. Path isolation and the POST token are enforced here without
using the spoofable ``Host`` header: a request through Serve with
``Host: 127.0.0.1`` cannot reach the full UI.

Only the capture page, static assets it needs, and the capture POST cross the
edge. Everything else is rejected before the main app sees it.
"""
from __future__ import annotations

from urllib.parse import unquote

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from spendtrack.security import (
    _CAPTURE_EDGE_MARKER,
    _capture_rate_ok,
    _capture_token_ok,
)

_DEFAULT_CAPTURE_PORT = 8767
_CAPTURE_POST_PATH = "/api/transactions"


def _json_error(status_code: int, detail: str) -> JSONResponse:
    response = JSONResponse({"detail": detail}, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _read_path_allowed(path: str) -> bool:
    """Remote GET/HEAD: capture page and the static assets it needs."""
    if path == "/capture":
        return True
    if not path.startswith("/static/"):
        return False
    # Do not let a static prefix smuggle dot segments or Windows separators past
    # the edge. Uvicorn usually decodes these already; decode defensively and
    # reject before the main app can normalize them into another route.
    decoded = unquote(path)
    if "\\" in decoded or "\x00" in decoded:
        return False
    return not any(part in {".", ".."} for part in decoded.split("/"))


class CaptureOnlyApp:
    """Hard edge around the main app; no ``Host`` header is trusted."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            # This app has no websocket surface; fail closed instead of forwarding.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        headers = Headers(scope=scope)

        if method in {"GET", "HEAD"} and _read_path_allowed(path):
            return await self.app(scope, receive, send)

        if method == "POST" and path == _CAPTURE_POST_PATH:
            if not _capture_token_ok(headers):
                response = _json_error(401, "capture token required")
                return await response(scope, receive, send)
            client = (scope.get("client") or ("unknown", 0))[0]
            if not _capture_rate_ok(client):
                response = _json_error(429, "rate limit exceeded")
                return await response(scope, receive, send)
            # Tell the app-level guard that this request was already checked at the
            # edge (same process), so the token/rate limit is not charged twice.
            state = scope.get("state")
            if state is None:
                state = scope["state"] = {}
            state[_CAPTURE_EDGE_MARKER] = True
            return await self.app(scope, receive, send)

        response = _json_error(403, "capture edge: path blocked")
        return await response(scope, receive, send)
