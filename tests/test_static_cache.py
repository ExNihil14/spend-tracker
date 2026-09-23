"""Кэш статики: версионированные URL → immutable; HTML → no-store (оффлайн, публичный интерфейс)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "cache.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_html_is_no_store(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"


def test_versioned_static_is_immutable(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/static/app.css?v=deadbeef")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"


def test_unversioned_static_revalidates(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/static/app.css")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"


def test_static_url_is_content_versioned() -> None:
    from spendtrack.assets import static_url

    first = static_url("app.css")
    assert first.startswith("/static/app.css?v=")
    assert len(first.split("?v=")[1]) == 12
    assert static_url("app.css") == first  # стабильно при неизменном файле
    assert static_url("app.js") != first


def test_static_url_is_thread_safe() -> None:
    """Версия считается из lru_cache — параллельные вызовы дают одно значение (threadpool FastAPI)."""
    from concurrent.futures import ThreadPoolExecutor

    from spendtrack.assets import static_url

    with ThreadPoolExecutor(max_workers=8) as pool:
        values = set(pool.map(lambda _: static_url("app.css"), range(32)))
    assert len(values) == 1
