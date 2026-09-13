from __future__ import annotations

import re
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _wait_htmx(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём завершения htmx-запроса и появления контента в целевом элементе."""
    page.wait_for_function(
        "() => window.htmx && !document.querySelector('.htmx-request')",
        timeout=timeout,
    )
    expect(page.locator(selector).first).not_to_be_empty(timeout=timeout)


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