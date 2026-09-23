"""Кросс-движковый смоук: рендер, отсутствие ошибок консоли, reflow 320px, axe (WCAG A/AA).

Запуск (все движки): uv run pytest tests/e2e/test_crossbrowser_smoke.py -m e2e --browser chromium --browser firefox --browser webkit
В CI: chromium — полный e2e-набор, firefox/webkit — только этот файл (см. .github/workflows/ci.yml).
"""
from __future__ import annotations

import contextlib

import pytest
from helpers import seed_smoke_data
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

PAGES = ("/", "/dashboard", "/approve", "/settings", "/help")
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


@pytest.fixture(autouse=True)
def _seeded(db_path) -> None:
    seed_smoke_data(db_path)


def _open(page: Page, base: str, path: str) -> list[str]:
    """Открывает страницу, возвращает ошибки консоли/pageerror (до навигации слушаем)."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    response = page.goto(base + path, wait_until="load")
    assert response is not None and response.ok, f"{path}: HTTP {response.status if response else '?'}"
    page.wait_for_selector("nav", state="visible")
    return errors


@pytest.mark.parametrize("path", PAGES)
def test_page_renders_without_console_errors(page: Page, live_server: str, path: str) -> None:
    errors = _open(page, live_server, path)
    assert errors == [], f"{path}: ошибки в консоли: {errors[:5]}"


@pytest.mark.parametrize("path", PAGES)
def test_no_horizontal_scroll_at_320(page: Page, live_server: str, path: str) -> None:
    """WCAG 1.4.10 Reflow: при 320 CSS px страница не требует двухмерного скролла."""
    page.set_viewport_size({"width": 320, "height": 640})
    _open(page, live_server, path)
    overflow = page.evaluate(
        "() => { const el = document.scrollingElement; return el.scrollWidth - el.clientWidth; }")
    assert overflow <= 0, f"{path}: горизонтальный скролл документа +{overflow}px на 320px"


@pytest.mark.parametrize("path", ("/", "/dashboard"))
def test_no_horizontal_scroll_after_resize(page: Page, live_server: str, path: str) -> None:
    """Реальное сужение окна (1280 → 320): canvas/гриды не должны выталкивать страницу.

    Отдельный сценарий от «старт с 320»: Chart.js получает контейнер 1280, затем ResizeObserver
    должен сжать его; ловушка — грид-элемент с `min-width: auto` (нужен `min-w-0`).
    """
    page.set_viewport_size({"width": 1280, "height": 800})
    _open(page, live_server, path)
    page.set_viewport_size({"width": 320, "height": 640})
    with contextlib.suppress(Exception):
        # детерминированное ожидание: Chart.js/ResizeObserver дожимают контейнер;
        # таймаут не маскирует финальную проверку — она даст детали (overflow в px)
        page.wait_for_function(
            "() => { const el = document.scrollingElement;"
            " return el.scrollWidth <= el.clientWidth; }", timeout=3000)
    overflow = page.evaluate(
        "() => { const el = document.scrollingElement; return el.scrollWidth - el.clientWidth; }")
    assert overflow <= 0, f"{path}: после resize 1280→320 горизонтальный скролл +{overflow}px"


def test_add_form_works_under_strict_csp(page: Page, live_server: str) -> None:
    """Интерактивный сценарий под строгим `script-src 'self'`: добавление без CSP-нарушений.

    Проверяет и перенос обработчиков в /static/app.js: форма сбрасывается после успешного ответа.
    """
    errors = _open(page, live_server, "/")
    page.fill('#add-form input[name="description"]', "ТЕСТ CSP")
    page.fill('#add-form input[name="amount"]', "-123.45")
    with page.expect_response(lambda r: "/api/transactions" in r.url):
        page.locator("#add-form button").click()
    page.wait_for_selector("#newmsg p")
    page.wait_for_function(
        "() => document.querySelector('#add-form input[name=\"description\"]').value === ''",
        timeout=3000)
    assert errors == [], f"CSP/консоль: {errors[:5]}"


def test_chart_js_loads_only_on_dashboard(page: Page, live_server: str) -> None:
    """Chart.js (~205 КБ) не грузится на списке; на дашборде — грузится и график нарисован."""
    _open(page, live_server, "/")
    page.wait_for_load_state("networkidle")  # все ресурсы страницы завершены (без фикс-паузы)
    on_index = page.evaluate("() => performance.getEntriesByType('resource').map(e => e.name)")
    assert not any("chart.umd" in r for r in on_index), "Chart.js загружен на /"

    _open(page, live_server, "/dashboard")
    page.wait_for_function(
        "() => window.Chart && window.Chart.getChart(document.getElementById('dailyChart'))",
        timeout=5000)
    on_dash = page.evaluate("() => performance.getEntriesByType('resource').map(e => e.name)")
    assert any("chart.umd" in r for r in on_dash)


def test_table_region_is_keyboard_focusable(page: Page, live_server: str) -> None:
    """Скролл-область таблицы достижима с клавиатуры и имеет видимый фокус (WCAG 2.1.1/2.4.7)."""
    _open(page, live_server, "/")
    page.locator(".table-scroll").first.focus()
    info = page.evaluate(
        "() => { const el = document.querySelector('.table-scroll');"
        " const s = getComputedStyle(el);"
        " return { tabindex: el.getAttribute('tabindex'), role: el.getAttribute('role'),"
        "          outlineWidth: parseFloat(s.outlineWidth) || 0 }; }")
    assert info["tabindex"] == "0" and info["role"] == "region"
    assert info["outlineWidth"] >= 1, f"фокус не виден: outline {info['outlineWidth']}"


@pytest.mark.parametrize("path", PAGES)
def test_axe_no_critical_or_serious_violations(page: Page, live_server: str, path: str) -> None:
    """axe (WCAG 2.1 A/AA): critical/serious — блокер; minor/moderate печатаем для разбора."""
    from axe_playwright_python.sync_playwright import Axe

    _open(page, live_server, path)
    results = Axe().run(page, options={
        "resultTypes": ["violations"],
        "runOnly": {"type": "tag", "values": AXE_TAGS},
    })
    violations = results.response["violations"]
    blockers = [f"{v['id']} ({v['impact']}, {len(v['nodes'])})"
                for v in violations if v.get("impact") in ("critical", "serious")]
    assert blockers == [], f"{path}: a11y-нарушения critical/serious: {blockers}"
    if violations:
        summary = ", ".join(f"{v['id']} ({v['impact']}, {len(v['nodes'])})" for v in violations)
        print(f"[axe] {path}: minor/moderate: {summary}")
