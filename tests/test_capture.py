"""Mobile quick-capture (`/capture`): один экран, существующий POST, без offline/PWA SW."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "capture.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_capture_page_is_one_screen_with_accessible_fields(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/capture")
        static_page = client.get("/static/capture.html")
        js = client.get("/static/capture.js")
    assert r.status_code == 200
    assert static_page.status_code == 200
    assert js.status_code == 200
    assert "X-Spendtrack-Token" in js.text
    assert "capture-client-id" in js.text
    body = r.text
    assert 'id="capture-form"' in body
    assert 'id="capture-client-id"' in body
    assert 'name="client_id"' in body
    assert 'id="capture-token"' in body
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


def test_capture_client_id_retry_is_idempotent_and_response_is_no_store(tmp_path, monkeypatch) -> None:
    form = {
        "date": "2026-11-01",
        "description": "КОФЕ С СОБОЙ",
        "amount": "-180",
        "client_id": "phone-retry-1",
    }
    with _client(tmp_path, monkeypatch) as client:
        first = client.post("/api/transactions", data=form, headers={"HX-Request": "true"})
        second = client.post("/api/transactions", data=form, headers={"HX-Request": "true"})
        json_response = client.post("/api/transactions", json={
            "date": "2026-11-01", "description": "ЧАЙ", "amount": "-50", "client_id": "phone-retry-2",
        })
    assert first.status_code == 200 and "Добавлено" in first.text
    assert second.status_code == 200 and "Не добавлено" in second.text
    assert json_response.status_code == 200
    assert json_response.headers["cache-control"] == "no-store"
