from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import _setup_logging, app
from spendtrack.store import Store


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
    assert "Ничего не найдено по этому фильтру" in r2.text
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

def test_import_limit_json_413(client):
    """Файл больше лимита → 413 с понятным текстом (а не 500)."""
    cyrillic = "ф" * (10 * 1024 * 1024 // 2 + 10)  # >10 МБ в байтах
    r = client.post("/api/import", json={"bank": "sber", "csv": cyrillic})
    assert r.status_code == 413
    assert "лимит" in r.json()["detail"]


def test_import_limit_htmx_shows_error(client):
    """HTMX-ветка: лимит показывается красным текстом, без 500 (ASCII: 1 байт/символ)."""
    big = "x" * (10 * 1024 * 1024 + 10)
    r = client.post("/api/import", data={"bank": "sber", "csv": big},
                    headers={"hx-request": "true"})
    assert r.status_code == 200
    assert "Ошибка импорта" in r.text


def test_import_hx_format_drift_shows_error_with_hint(client):
    """HTMX-ветка: дрейф формата → красный текст с просьбой прислать образец, БД не тронута."""
    csv_data = "Дата проводки;Назначение;Сумма\n01.09.2026;ЛЕНТА;100\n"
    r = client.post("/api/import", data={"bank": "auto", "csv": csv_data},
                    headers={"hx-request": "true"})
    assert r.status_code == 200
    assert "Ошибка импорта" in r.text
    assert "образец" in r.text
    assert client.get("/health").json()["transactions"] == 0


def test_import_invalid_json_body_gives_400(client):
    """Битое/не-UTF-8 тело: 400 с понятным текстом, а не 500 (live-смоук 21.09)."""
    r = client.post("/api/import", content=b'{"bank":"auto","csv":"\xff\xfe"}',
                    headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert "UTF-8" in r.json()["detail"]


def test_transactions_missing_fields_gives_422(client):
    """Неполный JSON → 422 (валидация), а не 500."""
    r = client.post("/api/transactions", json={"date": "2026-09-12"})
    assert r.status_code == 422


def test_import_json_format_error_status(client):
    """Не-HTML клиент получает JSON со статусом format_error и найденными колонками."""
    csv_data = "Дата проводки;Назначение;Сумма\n01.09.2026;ЛЕНТА;100\n"
    r = client.post("/api/import", json={"bank": "auto", "csv": csv_data})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "format_error"
    assert body["missing_columns"] == []  # банк не определён — конкретной нехватки нет
    assert "Дата проводки" in body["found_columns"]
    assert "образец" in body["message"]


def test_import_hx_report_shows_skipped_and_suspicious(client):
    """HTMX-отчёт: «+N добавлено · пропущено · подозрительно» с причинами."""
    csv_data = ("Дата;Сумма операции;Категория;Описание;Счёт\n"
                "02.09.2026;-1200,00;Транспорт;UBER MUNCHEN;4081781\n")
    r = client.post("/api/import", data={"bank": "auto", "csv": csv_data},
                    headers={"hx-request": "true"})
    assert "Импортировано" in r.text
    assert "+1 добавлено" in r.text
    assert "банк=tinkoff" in r.text


def test_form_missing_required_field_returns_422(client):
    """Форма без обязательного поля → 422 (как JSON-ветка), а не 500 (ресёрч слоёв 23.09)."""
    r = client.post("/api/transactions", data={"description": "БЕЗ СУММЫ"})
    assert r.status_code == 422


def test_import_hx_empty_and_generic_error(client, monkeypatch):
    """HX-ветки импорта: пустой файл и generic-исключение (аудит 23.09, P1)."""
    r = client.post("/api/import", data={"bank": "auto", "csv": ""},
                    headers={"hx-request": "true"})
    assert r.status_code == 200
    assert "Пустой файл" in r.text

    def boom(*args, **kwargs):
        raise RuntimeError("внезапный сбой")

    monkeypatch.setattr("spendtrack.routers.api.import_csv", boom)
    r2 = client.post("/api/import", data={"bank": "auto", "csv": "x"},
                     headers={"hx-request": "true"})
    assert r2.status_code == 200
    assert "Ошибка импорта" in r2.text and "внезапный сбой" in r2.text


def test_import_limit_error_hx_and_json(client, monkeypatch):
    """Лимит импорта: HX → понятный фрагмент, JSON → 413 (ветка api.py:280)."""
    from spendtrack.csv_import import ImportLimitError

    def too_big(*args, **kwargs):
        raise ImportLimitError("CSV превышает лимит 10 МБ (99999999 байт)")

    monkeypatch.setattr("spendtrack.routers.api.import_csv", too_big)
    r_hx = client.post("/api/import", data={"bank": "auto", "csv": "x"},
                       headers={"hx-request": "true"})
    assert r_hx.status_code == 200
    assert "Ошибка импорта" in r_hx.text
    r_json = client.post("/api/import", json={"bank": "auto", "csv": "x"})
    assert r_json.status_code == 413


def _seed_tx(tmp_path, description="АЗС", category_source="llm_pending_review",
             category="other", review_status="pending") -> int:
    """Прямая запись в ту же БД, что у client-фикстуры (env SPENDTRACK_DB_PATH)."""
    s = Store(db_path=tmp_path / "api.db")
    s.add_transaction(date="2026-09-10", description=description, amount_kopecks=-1000,
                      category=category, category_source=category_source, confidence=0.5,
                      category_llm="transport", review_status=review_status)
    tx_id = s.conn.execute("SELECT id FROM transactions ORDER BY id DESC LIMIT 1").fetchone()["id"]
    s.close()
    return tx_id


def test_reviews_count_endpoint(client, tmp_path):
    """GET /api/reviews/count — OOB-бейдж счётчика (аудит 23.09: роут без тестов)."""
    _seed_tx(tmp_path)
    r = client.get("/api/reviews/count")
    assert r.status_code == 200
    assert 'id="pending-count"' in r.text
    assert ">1<" in r.text


def test_review_and_tx_4xx_branches(client, tmp_path):
    """Ветки ошибок очереди/транзакций: approve/skip 404/409, PATCH/GET 404 (аудит 23.09)."""
    pending_id = _seed_tx(tmp_path)
    approved_id = _seed_tx(tmp_path, description="ЛЕНТА", category_source="rule",
                           category="groceries", review_status="approved")

    assert client.post("/api/reviews/999999/approve", data={"category": "other"}).status_code == 404
    assert client.post(f"/api/reviews/{approved_id}/approve",
                       data={"category": "other"}).status_code == 409
    assert client.post("/api/reviews/999999/skip").status_code == 404
    assert client.post(f"/api/reviews/{approved_id}/skip").status_code == 409
    assert client.patch("/api/transactions/999999",
                        json={"category": "other"}).status_code == 404

    r_ok = client.get(f"/api/transactions/{pending_id}")
    assert r_ok.status_code == 200
    assert r_ok.json()["description"] == "АЗС"
    assert client.get("/api/transactions/999999").status_code == 404


def test_health_503_when_db_unavailable(client, monkeypatch):
    """/health отдаёт 503, если БД не открывается (ветка main.py:104, аудит 23.09)."""
    class BrokenStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr("spendtrack.store.Store", BrokenStore)
    assert client.get("/health").status_code == 503


# ── M-6: импорт файлом (multipart) ──────────────────────────────────────────

def test_import_multipart_file_upload(client):
    """CSV из <input type=file> (multipart) импортируется; имя файла — источник партии."""
    csv_data = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
                "Валюта операции;Категория;Описание\n"
                "1;01.09.2026 10:00;1234;Выполнено;-1 234,56;RUB;Продукты;ЛЕНТА ФАЙЛ\n")
    r = client.post("/api/import", data={"bank": "sber"},
                    files={"file": ("sber.csv", csv_data.encode("utf-8"), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["added"] == 1
    assert client.get("/health").json()["transactions"] == 1


def test_import_multipart_cp1251_bytes(client):
    """Файл в cp1251 (реальный экспорт Т-Банка) читается байтами без «кракозябр»."""
    csv_data = ("Дата;Сумма операции;Категория;Описание;Счёт\n"
                "02.09.2026;-1200,00;Транспорт;АЗС ЛУКОЙЛ;4081781\n")
    r = client.post("/api/import", data={"bank": "auto"},
                    files={"file": ("tbank.csv", csv_data.encode("cp1251"), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["bank"] == "tinkoff" and body["added"] == 1


def test_import_multipart_empty_file_falls_back_to_text(client):
    """Пустой file (filename="") не ломает форму: используется текст из textarea."""
    csv_data = ("Дата;Сумма операции;Категория;Описание;Счёт\n"
                "02.09.2026;-1200,00;Транспорт;АЗС ЛУКОЙЛ;4081781\n")
    r = client.post("/api/import", data={"bank": "auto", "csv": csv_data},
                    files={"file": ("", b"", "application/octet-stream")})
    assert r.status_code == 200
    assert r.json()["added"] == 1
