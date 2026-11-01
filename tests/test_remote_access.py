"""Remote access guard: path isolation + rate limit for trusted HTTPS proxy/Tailscale."""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from spendtrack.security import _RemoteAccessGuard, _reset_capture_rate


@pytest.fixture(autouse=True)
def _trusted_proxy_env(monkeypatch):
    monkeypatch.setenv("SPENDTRACK_TRUSTED_HOSTS", "spend.tailnet.ts.net")


def _app() -> Starlette:
    async def home(_request):
        return PlainTextResponse("home")

    async def approve(_request):
        return PlainTextResponse("approve")

    async def capture(_request):
        return PlainTextResponse("capture")

    async def transactions(request):
        return PlainTextResponse("tx", status_code=200 if request.method == "POST" else 405)

    app = Starlette(routes=[
        Route("/", home),
        Route("/approve", approve),
        Route("/capture", capture),
        Route("/api/transactions", transactions, methods=["GET", "POST"]),
    ])
    app.add_middleware(_RemoteAccessGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["spend.tailnet.ts.net", "testserver"])
    return app


def test_remote_path_isolation_allows_capture_only() -> None:
    remote = {"Host": "spend.tailnet.ts.net"}
    with TestClient(_app()) as client:
        assert client.get("/", headers=remote).status_code == 403
        assert client.get("/approve", headers=remote).status_code == 403
        assert client.get("/capture", headers=remote).status_code == 200
        assert client.get("/api/transactions", headers=remote).status_code == 403
        assert client.post("/api/transactions", headers=remote).status_code == 200
        # control: loopback/test host keeps the full UI
        assert client.get("/", headers={"Host": "testserver"}).status_code == 200


def test_remote_capture_rate_limit() -> None:
    _reset_capture_rate()
    remote = {"Host": "spend.tailnet.ts.net"}
    with TestClient(_app()) as client:
        for _ in range(10):
            assert client.post("/api/transactions", headers=remote).status_code == 200
        blocked = client.post("/api/transactions", headers=remote)
    assert blocked.status_code == 429
    assert "rate limit" in blocked.text.lower()
    _reset_capture_rate()
