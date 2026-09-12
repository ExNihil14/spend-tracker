from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """API-тесты против временной БД через env (pydantic-settings читает SPENDTRACK_DB_PATH)."""
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "api.db"))
    return TestClient(app)


def test_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Spendtrack" in r.text


def test_create_transaction_rule_category(client):
    r = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-123.45",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "groceries"
    assert body["source"] == "rule"


def test_patch_category(client):
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-50.00",
    }).json()
    assert tx["id"] is not None
    r = client.patch(f"/api/transactions/{tx['id']}", json={"category": "household"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_patch_invalid_category_422(client):
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-50.00",
    }).json()
    r = client.patch(f"/api/transactions/{tx['id']}", json={"category": "hacker_cat"})
    assert r.status_code == 422


def test_import_endpoint(client):
    csv_data = "Дата;Сумма операции;Категория;Описание;Счёт\n02.09.2026;-1200,00;Транспорт;UBER MUNCHEN;4081781"
    r = client.post("/api/import", json={"bank": "tinkoff", "csv": csv_data})
    assert r.status_code == 200
    assert r.json()["added"] == 1