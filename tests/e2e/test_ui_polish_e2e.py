"""P2 UX-полировка в браузере: пустые состояния, знаки сумм, подсказки (e2e, оффлайн-сервер)."""
from __future__ import annotations

import re

import pytest
from helpers import seed_tx as _seed
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_empty_states_teach_first_step(page: Page, live_server):
    """Пустые список/очередь/дашборд объясняют первый шаг и ссылаются на /help."""
    page.goto(f"{live_server}/")
    expect(page.locator("#tx-table")).to_contain_text("Пока нет транзакций")
    expect(page.locator('#tx-table a[href="/help#faq-import-sber"]')).to_be_visible()

    page.goto(f"{live_server}/approve")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")
    expect(page.locator('#review-rows a[href="/help#faq-queue-why"]')).to_be_visible()

    page.goto(f"{live_server}/dashboard")
    expect(page.locator("#onboarding")).to_be_visible()
    expect(page.locator('#onboarding a[href="/#import"]')).to_be_visible()
    expect(page.locator('#onboarding a[href="/help#quick-start"]')).to_be_visible()


def test_first_run_checklist_visible_then_hidden(page: Page, live_server, db_path):
    """P2 #10: чек-лист 4 шагов виден на пустой базе и исчезает после первых данных."""
    page.goto(f"{live_server}/")
    expect(page.locator("#start-checklist")).to_be_visible()
    expect(page.locator("#start-checklist li")).to_have_count(4)
    _seed(str(db_path), "2026-09-10", "ЛЕНТА СТАРТ", -10000)
    page.goto(f"{live_server}/")
    expect(page.locator("#start-checklist")).to_have_count(0)


def test_amount_signs_and_badge_text_color(page: Page, live_server, db_path):
    """Расход/доход различаются знаком (−/+), а не только цветом; бейдж задаёт цвет текста."""
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ЗНАК", -12345)
    _seed(str(db_path), "2026-09-11", "ЗАРПЛАТА ЗНАК", 1234500)
    page.goto(live_server)
    table = page.locator("#tx-table")
    expect(table).to_contain_text("\u2212123,45 ₽")
    expect(table).to_contain_text("+12 345,00 ₽")
    badge = page.locator('#tx-table a[href*="category=groceries"]').first
    style = badge.get_attribute("style") or ""
    assert "background:" in style and "color:" in style
    assert "#020617" in style  # светлый цвет категории → тёмный текст (контраст ≥4.5:1)


def test_category_badge_keeps_month(page: Page, live_server, db_path):
    """Смоук-баг 23.09: бейдж категории не должен уводить в другой месяц и подменять только таблицу.

    Было: href без месяца + наследование hx-target/#tx-table → шапка «Июль», строки сентября.
    Стало: полная навигация с month= → согласованная страница (шапка/итоги/фильтр/таблица).
    """
    _seed(str(db_path), "2026-08-10", "ЛЕНТА АВГ", -7000)
    _seed(str(db_path), "2026-09-10", "ЛЕНТА СЕН", -8000)
    page.goto(f"{live_server}/?month=2026-08")
    expect(page.locator("h2", has_text="Транзакции Август 2026")).to_be_visible()
    page.locator('#tx-table a[href*="category=groceries"]').first.click()
    expect(page).to_have_url(re.compile(r"month=2026-08.*category=groceries"))
    expect(page.locator("h2", has_text="Транзакции Август 2026")).to_be_visible()
    expect(page.locator('#filters select[name="category"]')).to_have_value("groceries")
    expect(page.locator("#tx-table")).to_contain_text("ЛЕНТА АВГ")
    expect(page.locator("#tx-table")).not_to_contain_text("ЛЕНТА СЕН")


def test_month_empty_note(page: Page, live_server, db_path):
    """Пустой месяц при наличии данных: подсказка с импортом, а не пустая таблица без объяснений."""
    _seed(str(db_path), "2026-09-10", "ЛЕНТА МЕСЯЦ", -10000)
    page.goto(f"{live_server}/?month=2026-01")
    expect(page.locator("#tx-table")).to_contain_text("За Январь 2026 операций нет")
    page.goto(f"{live_server}/dashboard?month=2026-01")
    expect(page.locator("body")).to_contain_text("За Январь 2026 операций нет")
