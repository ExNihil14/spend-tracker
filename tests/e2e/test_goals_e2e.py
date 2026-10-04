"""Ф1 целей (e2e): пустое состояние, создание, прогресс с a11y, взнос, архив."""
from __future__ import annotations

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
