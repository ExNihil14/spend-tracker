"""Ф1 целей (e2e): пустое состояние, создание, прогресс с a11y, взнос, архив."""
from __future__ import annotations

import sqlite3

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_goals_empty_state_and_create(page: Page, live_server):
    page.goto(f"{live_server}/goals")
    expect(page.locator("#goals-list")).to_contain_text("Пока нет целей")
    page.fill('input[name="title"]', "Отпуск")
    page.fill('input[name="target"]', "100 000")
    page.click('form[hx-post="/api/goals"] button')
    expect(page.locator("#goals-list")).to_contain_text("Отпуск")
    # wave5 C1: локаторы привязаны к карточке цели (без .first) — порядок/чужие цели не влияют
    card = page.locator("article").filter(has_text="Отпуск")
    bar = card.locator('[role="progressbar"]')
    expect(bar).to_have_attribute("aria-valuenow", "0")
    expect(bar).to_have_attribute("aria-label", "Прогресс цели «Отпуск»: 0%")


def test_goals_allocate_and_archive(page: Page, live_server):
    page.goto(f"{live_server}/goals")
    page.fill('input[name="title"]', "Подушка")
    page.fill('input[name="target"]', "10 000")
    page.click('form[hx-post="/api/goals"] button')
    expect(page.locator("#goals-list")).to_contain_text("Подушка")

    # wave5 C1: все действия — в карточке «Подушка» (без .first по всей странице)
    card = page.locator("article").filter(has_text="Подушка")
    # a11y: у поля взноса есть accessible-имя
    amount = card.locator('input[name="amount"]')
    expect(amount).to_have_attribute("aria-label", "Сумма взноса: плюс — пополнение, минус — изъятие")
    amount.fill("2 500")
    card.locator('form[hx-post$="/allocate"] button').click()
    expect(card.locator('[role="progressbar"]')).to_have_attribute("aria-valuenow", "25")
    expect(page.locator("#goals-list")).to_contain_text("Журнал взносов")

    # архив (hx-confirm → принять диалог): карточка уходит из активных, остаётся в архиве
    page.on("dialog", lambda d: d.accept())
    card.locator('form[hx-post$="/archive"] button').click()
    expect(page.locator("#goals-list")).to_contain_text("Архив")
    expect(page.locator("article").filter(has_text="Подушка")).to_have_count(0)
    expect(card.locator('form[hx-post$="/allocate"]')).to_have_count(0)


def test_allocate_error_keeps_draft_date_and_focus(page: Page, live_server, db_path):
    """S8 (wave5): ошибка взноса не перерисовывает список — черновик, выбранная дата и фокус живы."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO goals(title, target_kopecks, currency, created_month, archived,"
                 " created, updated) VALUES('Черновик', 100000, 'RUB', '2026-10', 0, 't', 't')")
    conn.commit()
    conn.close()

    page.goto(f"{live_server}/goals")
    card = page.locator("article").filter(has_text="Черновик")
    amount = card.locator('input[name="amount"]')
    date_input = card.locator('input[name="date"]')
    amount.fill("abc")
    date_input.fill("2026-09-10")
    amount.focus()
    amount.press("Enter")
    expect(page.locator("#goals-error")).to_contain_text("Не получилось")
    assert amount.input_value() == "abc"              # черновик не сброшен
    assert date_input.input_value() == "2026-09-10"   # выбранная дата сохранена
    assert amount.evaluate("el => document.activeElement === el"), "фокус ушёл из поля суммы"
