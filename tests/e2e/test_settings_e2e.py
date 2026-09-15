from __future__ import annotations

import sqlite3

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

BROAD = "E2E ПАТТЕРН"
NARROW = "E2E ПАТТЕРН 24"


def _wait_single(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём, пока htmx завершит swap (settling) и останется ровно один элемент."""
    page.wait_for_function(
        "(sel) => window.htmx && !document.querySelector('.htmx-request')"
        " && document.querySelectorAll(sel).length === 1",
        arg=selector,
        timeout=timeout,
    )


def _patterns(page: Page) -> list[str]:
    return page.locator("#settings-rules tbody tr").evaluate_all(
        "els => els.map(e => e.dataset.pattern)")


def _add_rule(page: Page, pattern: str, category: str = "other") -> None:
    page.fill('#settings-rules input[name="pattern"]', pattern)
    page.select_option('#settings-rules select[name="category"]', category)
    page.click('#settings-rules form[hx-post="/settings/rules"] button[type="submit"]')
    _wait_single(page, "#settings-rules")


def test_rule_lifecycle_add_move_delete(page: Page, live_server, taxonomy_path):
    """Полный цикл: добавление в конец → ↑ (swap) → удаление с подтверждением."""
    page.goto(f"{live_server}/settings")
    _add_rule(page, BROAD)
    before = _patterns(page)
    assert before[-1] == BROAD

    row = page.locator(f'tr[data-pattern="{BROAD}"]')
    row.locator('button[title="Переместить выше"]').click()
    _wait_single(page, "#settings-rules")
    after = _patterns(page)
    assert after.index(BROAD) == before.index(BROAD) - 1

    page.on("dialog", lambda d: d.accept())
    page.locator(f'tr[data-pattern="{BROAD}"] button[title="Удалить правило"]').click()
    _wait_single(page, "#settings-rules")
    expect(page.locator(f'tr[data-pattern="{BROAD}"]')).to_have_count(0)
    assert BROAD not in taxonomy_path.read_text(encoding="utf-8")


def test_category_rename_migrates_transactions(page: Page, live_server, db_path):
    """Переименование категории из UI: подтверждение с числом строк + миграция БД."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
        " confidence, created, updated)"
        " VALUES('2026-09-12', 'E2E ПЕРЕИМЕНОВАНИЕ', -100, 'other', 'manual', 1.0,"
        " datetime('now'), datetime('now'))")
    conn.commit()
    conn.close()

    page.goto(f"{live_server}/settings")
    rename_form = 'form[hx-post="/settings/categories/rename/preview"]'
    page.select_option(f'{rename_form} select[name="name"]', "other")
    page.fill(f'{rename_form} input[name="new_name"]', "general")
    page.click(f"{rename_form} button")
    expect(page.locator("#rename-confirm")).to_contain_text("транзакций 1", timeout=10_000)

    page.click('#rename-confirm button:has-text("Подтвердить")')
    _wait_single(page, "#settings-categories")
    expect(page.locator("#settings-categories")).to_contain_text("general")

    conn = sqlite3.connect(str(db_path))
    migrated = conn.execute("SELECT category FROM transactions").fetchone()[0]
    conn.close()
    assert migrated == "general"


def test_rule_dead_badge_and_preview(page: Page, live_server):
    """Ниже широкого правила узкое становится «мёртвым»; предпросмотр ловит дубль."""
    page.goto(f"{live_server}/settings")
    _add_rule(page, BROAD)
    _add_rule(page, NARROW)

    expect(page.locator(f'tr[data-pattern="{NARROW}"]')).to_contain_text("мёртвое")
    expect(page.locator("#settings-rules")).to_contain_text("Мёртвых правил")

    page.fill('#settings-rules input[name="pattern"]', BROAD)
    expect(page.locator("#rule-preview")).to_contain_text("дубль", timeout=10_000)
