"""Периметр локального приложения: Origin/Sec-Fetch-гейт и TrustedHost (без аутентификации)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from spendtrack.security import origin_allowed


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "perimeter.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_origin_allowed_matrix() -> None:
    # Origin есть → только loopback-имена (порт любой), схема http/https
    assert origin_allowed("http://127.0.0.1:8766", None) is True
    assert origin_allowed("http://localhost:8799", None) is True
    assert origin_allowed("https://evil.example", None) is False
    assert origin_allowed("http://127.0.0.1.evil.example", None) is False
    assert origin_allowed("javascript:alert(1)", None) is False
    assert origin_allowed("ftp://127.0.0.1", None) is False
    # Origin нет, есть Sec-Fetch-Site
    assert origin_allowed(None, "same-origin") is True
    assert origin_allowed(None, "none") is True
    assert origin_allowed(None, "cross-site") is False
    # Ничего нет → не браузер (CLI/тесты) — пропускаем
    assert origin_allowed(None, None) is True


def test_cross_origin_post_blocked(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/transactions", json={}, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        r2 = client.post("/api/transactions", json={}, headers={"Sec-Fetch-Site": "cross-site"})
        assert r2.status_code == 403


def test_same_origin_and_no_header_posts_pass_perimeter(tmp_path, monkeypatch) -> None:
    tx = {"date": "2026-09-01", "description": "ТЕСТ ПЕРИМЕТРА", "amount": "-100"}
    with _client(tmp_path, monkeypatch) as client:
        same_origin = client.post("/api/transactions", json=tx,
                                  headers={"Origin": "http://127.0.0.1:8766"})
        assert same_origin.status_code == 200, same_origin.text
        no_headers = client.post("/api/transactions", json=tx)  # TestClient/CLI-стиль
        assert no_headers.status_code == 200, no_headers.text


def test_get_with_foreign_origin_not_blocked(tmp_path, monkeypatch) -> None:
    """Гейт — только для state-changing методов; безопасные методы не ломаем."""
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/", headers={"Origin": "https://evil.example"}).status_code == 200
        for method in ("head", "options"):
            r = getattr(client, method)("/", headers={"Origin": "https://evil.example"})
            assert r.status_code != 403, f"{method}: {r.status_code}"


def test_blocked_response_keeps_security_headers(tmp_path, monkeypatch) -> None:
    """403 от origin-guard тоже обязан нести CSP/nosniff/referrer (порядок middleware)."""
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/transactions", json={}, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        assert "script-src 'self'" in r.headers.get("content-security-policy", "")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("referrer-policy") == "no-referrer"


def test_trusted_host_rejects_foreign_host(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
        assert client.get("/", headers={"Host": "localhost:8766"}).status_code == 200


def test_codespaces_disabled_by_default(monkeypatch) -> None:
    """Без CODESPACES домен форвардинга не принимается (локальный прод не расширяется)."""
    monkeypatch.delenv("CODESPACES", raising=False)
    from spendtrack.security import content_security_policy, origin_allowed, trusted_hosts

    assert "*.app.github.dev" not in trusted_hosts()
    assert origin_allowed("https://foo-8766.app.github.dev", None) is False
    assert "frame-ancestors 'none'" in content_security_policy()


def test_codespaces_env_allows_forwarded_host_origin_and_frame(monkeypatch) -> None:
    """Codespaces: прокси сохраняет Host `*-<port>.app.github.dev` → разрешаем домен форвардинга."""
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    from spendtrack.security import content_security_policy, origin_allowed, trusted_hosts

    assert "*.app.github.dev" in trusted_hosts()
    assert origin_allowed("https://foo-8766.app.github.dev", None) is True
    assert origin_allowed("https://evil.example", None) is False
    assert "frame-ancestors 'self' https://*.app.github.dev" in content_security_policy()


def test_codespaces_trusted_host_middleware_accepts_forwarded_host(monkeypatch) -> None:
    """Смоук связки: TrustedHostMiddleware с trusted_hosts() пропускает codespace-Host и режет чужой."""
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    from starlette.applications import Starlette
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient as StarletteTestClient

    from spendtrack.security import trusted_hosts

    async def _home(_request):
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/", _home)])
    inner.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts())
    with StarletteTestClient(inner) as client:
        assert client.get("/", headers={"Host": "foo-8766.app.github.dev"}).status_code == 200
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
