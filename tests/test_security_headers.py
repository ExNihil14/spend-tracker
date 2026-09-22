"""Заголовки безопасности (CSP и базовые) — оффлайн, публичный интерфейс приложения."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "sec.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_security_headers_present(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    for directive in ("default-src 'self'", "object-src 'none'", "base-uri 'self'",
                      "frame-ancestors 'none'", "form-action 'self'", "img-src 'self' data:"):
        assert directive in csp, directive
    # Строгий script-src: inline/hx-on вынесены в /static/app.js, htmx allowEval=false
    assert "script-src 'self'" in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_security_headers_on_api_and_static(tmp_path, monkeypatch) -> None:
    """Заголовки не только на страницах: API-ответы и статика тоже."""
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/health").headers.get("x-content-type-options") == "nosniff"
        assert client.get("/static/app.css").headers.get("content-security-policy")
