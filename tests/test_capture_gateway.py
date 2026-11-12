"""Capture-only edge: remote surface is independent of the spoofable Host header."""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from spendtrack.capture_gateway import CaptureOnlyApp, _read_path_allowed
from spendtrack.security import _RemoteAccessGuard, _reset_capture_rate


@pytest.fixture(autouse=True)
def _capture_env(monkeypatch):
    monkeypatch.setenv("SPENDTRACK_TRUSTED_HOSTS", "spend.tailnet.ts.net")
    monkeypatch.setenv("SPENDTRACK_CAPTURE_TOKEN", "test-capture-token")
    _reset_capture_rate()
    yield
    _reset_capture_rate()


def _inner_app() -> Starlette:
    async def echo(request):
        return PlainTextResponse(f"{request.method} {request.url.path}")

    return Starlette(routes=[
        Route("/", echo),
        Route("/approve", echo),
        Route("/settings", echo),
        Route("/capture", echo),
        Route("/static/capture.js", echo),
        Route("/api/transactions", echo, methods=["GET", "POST"]),
    ])


def _client(app=None) -> TestClient:
    return TestClient(CaptureOnlyApp(app or _inner_app()), base_url="http://127.0.0.1")


def test_loopback_host_cannot_open_main_ui_on_capture_edge() -> None:
    """CAP-01: a spoofed Host must not turn the capture edge into the full UI."""
    spoofed = {"Host": "127.0.0.1"}
    with _client() as client:
        assert client.get("/", headers=spoofed).status_code == 403
        assert client.get("/approve", headers=spoofed).status_code == 403
        assert client.get("/settings", headers=spoofed).status_code == 403
        assert client.get("/api/transactions", headers=spoofed).status_code == 403
        assert client.post("/api/transactions", headers=spoofed).status_code == 401


def test_capture_edge_allows_only_capture_page_static_and_token_post() -> None:
    headers = {"Host": "spend.tailnet.ts.net"}
    authorized = {**headers, "X-Spendtrack-Token": "test-capture-token"}
    with _client() as client:
        assert client.get("/capture", headers=headers).status_code == 200
        assert client.get("/static/capture.js", headers=headers).status_code == 200
        assert client.get("/", headers=headers).status_code == 403
        assert client.post("/api/transactions", headers=headers).status_code == 401
        assert client.post(
            "/api/transactions", headers={**headers, "X-Spendtrack-Token": "wrong"}
        ).status_code == 401
        assert client.post("/api/transactions", headers=authorized).status_code == 200


def test_capture_edge_rate_limit_is_enforced_once() -> None:
    headers = {
        "Host": "spend.tailnet.ts.net",
        "X-Spendtrack-Token": "test-capture-token",
    }
    with _client() as client:
        for _ in range(10):
            assert client.post("/api/transactions", headers=headers).status_code == 200
        assert client.post("/api/transactions", headers=headers).status_code == 429


@pytest.mark.parametrize("path", [
    "/static/../approve",
    "/static/%2e%2e/approve",
    "/static/..%5capprove",
    "/static/./capture.js",
    "/static/foo%2f..%2fapprove",
])
def test_read_path_allowed_rejects_static_traversal(path: str) -> None:
    """Static allow-list must not become a path-normalization bypass."""
    assert _read_path_allowed(path) is False


def test_read_path_allowed_keeps_real_static_assets() -> None:
    assert _read_path_allowed("/static/capture.js") is True
    assert _read_path_allowed("/capture") is True


def test_capture_edge_only_accepts_token_header() -> None:
    """A token in the query string is not a substitute for the required header."""
    with _client() as client:
        response = client.post(
            "/api/transactions?x-spendtrack-token=test-capture-token",
            headers={"Host": "spend.tailnet.ts.net"},
        )
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), [
    ("POST", "/capture"),
    ("PUT", "/api/transactions"),
    ("DELETE", "/api/transactions"),
    ("OPTIONS", "/api/transactions"),
    ("GET", "/capture/"),
    ("GET", "/api/transactions/"),
])
def test_capture_edge_blocks_non_allowlisted_methods_and_paths(
    method: str, path: str,
) -> None:
    with _client() as client:
        response = client.request(method, path, headers={"Host": "spend.tailnet.ts.net"})
    assert response.status_code == 403


def test_capture_edge_keeps_cross_origin_guard_after_edge_marker() -> None:
    """The same-process marker must not disable the app's CSRF Origin gate."""
    from spendtrack.main import app as main_app

    headers = {
        "Host": "127.0.0.1",
        "X-Spendtrack-Token": "test-capture-token",
        "Origin": "https://evil.example",
    }
    with TestClient(CaptureOnlyApp(main_app), base_url="http://127.0.0.1") as client:
        response = client.post("/api/transactions", headers=headers, data={})
    assert response.status_code == 403


def test_real_app_capture_edge_blocks_cap01_with_spoofed_host() -> None:
    from spendtrack.main import app as main_app

    spoofed = {"Host": "127.0.0.1"}
    with TestClient(CaptureOnlyApp(main_app), base_url="http://127.0.0.1") as client:
        assert client.get("/capture", headers=spoofed).status_code == 200
        assert client.get("/", headers=spoofed).status_code == 403
        assert client.get("/approve", headers=spoofed).status_code == 403
        assert client.get("/settings", headers=spoofed).status_code == 403
        assert client.post("/api/transactions", headers=spoofed).status_code == 401


def test_capture_edge_does_not_double_charge_guard_layers() -> None:
    inner = _inner_app()
    inner.add_middleware(TrustedHostMiddleware, allowed_hosts=["spend.tailnet.ts.net"])
    inner.add_middleware(_RemoteAccessGuard)
    headers = {
        "Host": "spend.tailnet.ts.net",
        "X-Spendtrack-Token": "test-capture-token",
    }
    with _client(inner) as client:
        for _ in range(10):
            assert client.post("/api/transactions", headers=headers).status_code == 200
        assert client.post("/api/transactions", headers=headers).status_code == 429


def test_capture_edge_non_ascii_token_is_unauthorized() -> None:
    """Non-ASCII header bytes must be rejected, not raise TypeError in compare_digest."""
    with _client() as client:
        response = client.post(
            "/api/transactions",
            headers={
                b"host": b"spend.tailnet.ts.net",
                b"x-spendtrack-token": b"\xff",
            },
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "capture token required"}
