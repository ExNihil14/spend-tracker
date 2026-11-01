"""Mobile quick-capture (`/capture`): один экран, существующий POST, без offline/PWA SW."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

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
        changed = client.post("/api/transactions", json={
            **form, "amount": "-181",
        })
        json_response = client.post("/api/transactions", json={
            "date": "2026-11-01", "description": "ЧАЙ", "amount": "-50", "client_id": "phone-retry-2",
        })
    assert first.status_code == 200 and "Добавлено" in first.text
    assert second.status_code == 200 and "Не добавлено" in second.text
    assert changed.status_code == 409
    assert changed.json()["detail"] == "client_id already used"
    assert json_response.status_code == 200
    assert json_response.headers["cache-control"] == "no-store"
    count = sqlite3.connect(tmp_path / "capture.db").execute(
        "SELECT COUNT(*) FROM capture_idempotency WHERE client_id = ?", ("phone-retry-1",)
    ).fetchone()[0]
    assert count == 1


def test_capture_client_id_concurrent_race_creates_one_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "capture.db"))
    from spendtrack.main import app

    payloads = [
        {"date": "2026-11-01", "description": "РАЗ", "amount": "-100", "client_id": "race-1"},
        {"date": "2026-11-01", "description": "ДВА", "amount": "-200", "client_id": "race-1"},
    ]
    clients = [TestClient(app), TestClient(app)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda pair: pair[0].post("/api/transactions", json=pair[1]),
            zip(clients, payloads),
        ))
    statuses = [r.status_code for r in results]
    for index, status in enumerate(statuses):
        if status == 503:  # SQLite busy: повтор после освобождения — strict client_id → 409
            retry = clients[index].post("/api/transactions", json=payloads[index])
            assert retry.status_code == 409
            statuses[index] = 409
    for client in clients:
        client.close()
    assert sorted(statuses) == [200, 409]
    rows = sqlite3.connect(tmp_path / "capture.db").execute(
        "SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert rows == 1
