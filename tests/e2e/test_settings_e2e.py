from __future__ import annotations

import sqlite3
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

BROAD = "E2E ПАТТЕРН"
NARROW = "E2E ПАТТЕРН 24"
PATTERN_INPUT = '#settings-rules input[name="pattern"]'


def _preview(page: Page, pattern: str) -> str:
    """Дождаться превью ИМЕННО для `pattern` (по телу запроса) и вернуть HTML ответа.

    Слепой `fill` + `to_contain_text` был гонкой (флейк CI 16.09): дебаунсенные запросы
    прошлых действий и пустой ответ «паттерн <2 символов» могли переписать #rule-preview
    позже нашего, и тест ждал текст, которого в итоге нет.
    """
    page.fill(PATTERN_INPUT, "")  # сброс: гарантируем changed-событие
    with page.expect_response(
        lambda r: "/settings/rules/preview" in r.url
        and parse_qs(r.request.post_data or "").get("pattern") == [pattern]
    ) as response:
        page.fill(PATTERN_INPUT, pattern)
    return response.value.text()


def _wait_single(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём, пока htmx завершит swap ЦЕЛИКОМ: запрос + settle (processNode).

    Ловушка (флейк CI 16.09→20.09): `.htmx-request` снимается в onload ДО settle,
    а новый контент получает обработчики htmx только в settle (`defaultSettleDelay=20ms`,
    `makeAjaxLoadTask` → `processNode`). Маркер незрелого контента — класс `htmx-added`
    (навешивается при вставке, снимается вместе с processNode). Без этой проверки
    `fill` попадал в инпут без слушателей и без baseline `changed`: превью-запрос
    не уходил вовсе (0 htmx:trigger), и следующий одинаковый fill считался «не changed».
    """
    page.wait_for_function(
        "(sel) => window.htmx && !document.querySelector('.htmx-request')"
        " && !document.querySelector('.htmx-added')"
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


def test_budget_set_and_dashboard_bar(page: Page, live_server, db_path):
    """Бюджет задаётся в /settings и показывается баром на /dashboard."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
        " confidence, created, updated)"
        " VALUES('2026-09-10', 'E2E БЮДЖЕТ', -150000, 'groceries', 'rule', 1.0,"
        " datetime('now'), datetime('now'))")
    conn.commit()
    conn.close()

    page.goto(f"{live_server}/settings")
    form = page.locator('form[hx-post="/settings/budgets"]:has(input[value="groceries"])')
    form.locator('input[name="amount"]').fill("2000")
    form.locator('input[name="amount"]').press("Enter")  # change/submit → автосохранение (M-7 + ревью 24.09)
    _wait_single(page, "#settings-budgets")

    page.goto(f"{live_server}/dashboard")
    expect(page.locator("body")).to_contain_text("Бюджеты месяца")
    expect(page.locator("body")).to_contain_text("1 500,00 ₽ / 2 000,00 ₽")
    expect(page.locator("body")).to_contain_text("75%")


def test_color_autosave_toast(page: Page, live_server):
    """M-7: цвет сохраняется по change (кнопки OK нет), появляется тост «Сохранено»."""
    page.goto(f"{live_server}/settings")
    color = page.locator('#settings-categories input[type="color"]').first
    with page.expect_response(lambda r: "/settings/categories/color" in r.url):
        color.evaluate(
            "el => { el.value = '#ff0000'; el.dispatchEvent(new Event('change', {bubbles: true})); }")
    expect(page.locator("#toast")).to_contain_text("Сохранено")


def test_rule_dead_badge_and_preview(page: Page, live_server):
    """Ниже широкого правила узкое становится «мёртвым»; предпросмотр ловит дубль."""
    page.goto(f"{live_server}/settings")
    _add_rule(page, BROAD)
    _add_rule(page, NARROW)

    expect(page.locator(f'tr[data-pattern="{NARROW}"]')).to_contain_text("мёртвое")
    expect(page.locator("#settings-rules")).to_contain_text("Мёртвых правил")

    body = _preview(page, BROAD)
    assert "дубль" in body, body
    expect(page.locator("#rule-preview")).to_contain_text("дубль", timeout=10_000)
