"""Mobile quick-capture (`/capture`): один экран, существующий POST, без offline/PWA SW."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "capture.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_capture_page_is_one_screen_with_accessible_fields(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/static/capture.html")
    assert r.status_code == 200
    body = r.text
    assert 'id="capture-form"' in body
    for field in ("date", "amount", "description"):
        assert f'name="{field}"' in body
        assert f'for="capture-{field}"' in body
    assert "Быстрый ввод" in body
    # Нет offline/PWA-обещаний: страница — thin client, очередь отдельным тикетом.
    assert "serviceWorker" not in body
    assert "manifest" not in body.lower()


def test_capture_posts_via_existing_api_and_reports_duplicate(tmp_path, monkeypatch) -> None:
    headers = {"HX-Request": "true"}
    form = {"date": "2026-11-01", "description": "КОФЕ", "amount": "-120"}
    with _client(tmp_path, monkeypatch) as client:
        first = client.post("/api/transactions", data=form, headers=headers)
        second = client.post("/api/transactions", data=form, headers=headers)
    assert first.status_code == 200
    assert "Добавлено" in first.text
    assert second.status_code == 200
    assert "Не добавлено" in second.text
