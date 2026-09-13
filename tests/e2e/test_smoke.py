from __future__ import annotations

import re
import sqlite3
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _seed_pending(conn_str: str, rows: list[tuple]) -> None:
    """Засеять pending-транзакции напрямую в БД (обход LLM): (fp, date, desc, sum, conf, llm_cat)."""
    conn = sqlite3.connect(conn_str)
    for fp, date, desc, amount_kopecks, conf, llm_cat in rows:
        conn.execute(
            """INSERT INTO transactions
               (fingerprint, date, description, amount_kopecks, category,
                category_source, confidence, category_llm, review_status,
                created, updated)
               VALUES (?, ?, ?, ?, 'other', 'llm_pending_review', ?, ?, 'pending',
                       datetime('now'), datetime('now'))""",
            (fp, date, desc, amount_kopecks, conf, llm_cat),
        )
    conn.commit()
    conn.close()


def _wait_htmx(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём завершения htmx-запроса и появления контента в целевом элементе."""
    page.wait_for_function(
        "() => window.htmx && !document.querySelector('.htmx-request')",
        timeout=timeout,
    )
    expect(page.locator(selector).first).not_to_be_empty(timeout=timeout)


def _wait_single(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём, пока htmx завершит swap (settling) и останется ровно один элемент."""
    page.wait_for_function(
        "(sel) => window.htmx && !document.querySelector('.htmx-request')"
        " && document.querySelectorAll(sel).length === 1",
        arg=selector,
        timeout=timeout,
    )


def test_add_transaction_rule_keyword(page: Page, live_server):
    """Добавление через UI: «ЛЕНТА» матчится keyword-правилом → groceries без LLM."""
    page.goto(live_server)
    page.fill('input[name="date"]', "2026-09-12")
    page.fill('input[name="description"]', "ЛЕНТА")
    page.fill('input[name="amount"]', "-1234.56")
    page.click('form[hx-post="/api/transactions"] button')
    _wait_htmx(page, "#newmsg")
    expect(page.locator("#newmsg").first).to_contain_text(re.compile(r"добавлен|ok", re.IGNORECASE))
    # refresh-list from:body должен перерисовать таблицу
    expect(page.locator("#tx-table")).to_contain_text("ЛЕНТА")


def test_filter_search_htmx(page: Page, live_server):
    """Поиск по q: htmx-фильтр запрашивает новую таблицу."""
    marker = f"ЛЕНТА{uuid4().hex[:6]}"
    with page.expect_response(lambda r: "/api/transactions" in r.url and r.request.method == "POST"):
        page.goto(live_server)
        page.fill('input[name="date"]', "2026-09-12")
        page.fill('input[name="description"]', marker)
        page.fill('input[name="amount"]', "-100.00")
        page.click('form[hx-post="/api/transactions"] button')
    _wait_htmx(page, "#newmsg")
    expect(page.locator("#tx-table")).to_contain_text(marker)
    # теперь поиск: уникальный мерчант → RSS только его
    page.fill('input[name="q"]', marker)
    _wait_htmx(page, "#tx-table")
    expect(page.locator("#tx-table")).to_contain_text(marker)


def test_import_csv_via_ui(page: Page, live_server):
    """Импорт Сбер-CSV через UI: выбран банк, вставлены строки, фрагмент в #importmsg."""
    page.goto(live_server)
    csv = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
        "Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;-1 234,56;RUB;Продукты;ЛЕНТА\n"
    )
    page.select_option('select[name="bank"]', "sber")
    page.fill('textarea[name="csv"]', csv)
    page.click('form[hx-post="/api/import"] button')
    _wait_htmx(page, "#importmsg")
    expect(page.locator("#importmsg").first).to_contain_text(re.compile(r"добавлено", re.IGNORECASE))


def test_health_endpoint(page: Page, live_server):
    """/health отвечает JSON-статусом на живом сервере."""
    page.goto(f"{live_server}/health")
    expect(page.locator("body")).to_contain_text('"status"')


# ── Approve-очередь ─────────────────────────────────────────────────────────

def test_approve_queue_skip(page: Page, live_server, db_path):
    """Пропуск pending-транзакции удаляет строку из очереди."""
    _seed_pending(str(db_path), [("fp-skip", "2026-09-12", "АЗС ЛУКОЙЛ", -15000, 0.65, "transport")])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("АЗС ЛУКОЙЛ")
    expect(page.locator("#review-rows")).to_contain_text("transport")

    page.locator("#review-1 form button").click()
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")


def test_approve_queue_approve_via_select(page: Page, live_server, db_path):
    """Смена категории в <select> approve'ит транзакцию (hx-swap=delete)."""
    _seed_pending(str(db_path), [
        ("fp-a1", "2026-09-12", "КАФЕ МОЛОКО",  -5000, 0.55, "food"),
        ("fp-a2", "2026-09-13", "АЗС ЛУКОЙЛ",  -15000, 0.65, "transport"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-1")).to_contain_text("КАФЕ МОЛОКО")

    # одобряем первую через смену категории в select
    page.locator("#review-1 select[name='category']").select_option("groceries")
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-1")).to_have_count(0)
    expect(page.locator("#review-2")).to_contain_text("АЗС ЛУКОЙЛ")


def test_approve_all_button(page: Page, live_server, db_path):
    """Кнопка «Одобрить все» убирает все pending-строки."""
    _seed_pending(str(db_path), [
        ("fp-b1", "2026-09-12", "ЛЕНТА А", -3000, 0.7, "groceries"),
        ("fp-b2", "2026-09-13", "Яндекс Такси", -2000, 0.5, "transport"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("ЛЕНТА А")
    expect(page.locator("#review-rows")).to_contain_text("Яндекс Такси")

    # auto-accept confirm dialog
    page.on("dialog", lambda d: d.accept())
    page.click("button:has-text('Одобрить все')")
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")


def test_approve_empty_queue(page: Page, live_server):
    """Пустая очередь показывает сообщение."""
    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")