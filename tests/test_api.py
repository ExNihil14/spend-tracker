from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import _setup_logging, app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """API-тесты против временной БД через env (pydantic-settings читает SPENDTRACK_DB_PATH)."""
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "api.db"))
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "transactions": 0}


def test_api_budgets(client):
    """Бюджеты: настройка через /settings, прогресс через GET /api/budgets (месяц последней транзакции)."""
    r = client.post("/settings/budgets", data={"category": "groceries", "amount": "2000"})
    assert r.status_code == 200
    client.post("/api/transactions", json={"date": "2026-09-10", "description": "ЛЕНТА", "amount": "-500"})
    body = client.get("/api/budgets?month=2026-09").json()
    assert body["month"] == "2026-09"
    item = {i["category"]: i for i in body["items"]}["groceries"]
    assert (item["budget_k"], item["spent_k"], item["pct"]) == (200_000, 50_000, 25.0)

    body2 = client.get("/api/budgets").json()  # месяц не задан → из последней транзакции
    assert body2["month"] == "2026-09"


def test_logging_idempotent():
    """Повторный вызов _setup_logging() не плодит handler'ы (дублирование строк в файле)."""
    before = [h for h in logging.getLogger("spendtrack").handlers]
    _setup_logging()
    _setup_logging()
    after = [h for h in logging.getLogger("spendtrack").handlers]
    assert len(after) == max(len(before), 1)  # 1 настроенный handler, не 2


def test_create_transaction_rule_category(client):
    r = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-123.45",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "groceries"
    assert body["source"] == "rule"


def test_create_transaction_htmx_form(client):
    """htmx-форма шлёт application/x-www-form-urlencoded, а не JSON."""
    r = client.post("/api/transactions", data={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-123.45",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "groceries"


def test_create_transaction_hx_request_html(client):
    """htmx-запрос (HX-Request: true) должен вернуть HTML-фрагмент, JSON-API не трогаем."""
    head = {"hx-request": "true"}
    r = client.post("/api/transactions", data={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-123.45",
    }, headers=head)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Добавлено" in r.text
    assert "groceries" in r.text


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


def test_pending_count(client):
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.get("/api/pending-count")
    assert r.status_code == 200
    assert r.json()["count"] >= 0


def test_index_category_and_search_filters(client):
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "ЛЕНТА", "amount": "-50.00",
    })
    r = client.get("/?category=groceries")
    assert r.status_code == 200
    assert "ЛЕНТА" in r.text
    r2 = client.get("/?category=household")
    assert r2.status_code == 200
    assert "ЛЕНТА" not in r2.text
    assert "Пусто" in r2.text
    r3 = client.get("/?q=ЛЕНТА")
    assert r3.status_code == 200
    assert "ЛЕНТА" in r3.text
    assert "СТРОЙКАОПТ" not in r3.text


def test_import_hx_request_returns_html(client):
    """htmx-форма импорта шлёт HX-Request → получает HTML-фрагмент, не JSON."""
    csv_data = "Тип операции;Дата;Номер карты;Статус;Сумма операции;Валюта операции;Описание\n" \
               "Перевод с карты;20.02.2026;****1234;Выполнено;-1 234,56;RUB;ЛЕНТА\n"
    r = client.post("/api/import", json={"bank": "sber", "csv": csv_data},
                    headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "<p" in r.text
    assert "+1 добавлено" in r.text
    assert "банк=sber" in r.text
    assert "<script" not in r.text


def test_import_json_client_gets_json(client):
    """Обычный JSON-клиент (curl/CLI) → JSON, не фрагмент."""
    csv_data = "Дата;Сумма операции;Категория;Описание;Счёт\n02.09.2026;-1200,00;Транспорт;UBER MUNCHEN;4081781"
    r = client.post("/api/import", json={"bank": "tinkoff", "csv": csv_data})
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
    assert r.json()["added"] >= 1
    assert "<p" not in r.text