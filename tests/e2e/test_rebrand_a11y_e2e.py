"""Ребрендинг 29.09: a11y-инварианты графиков и моушена (e2e, офлайн-сервер)."""
from __future__ import annotations

import re

import pytest
from helpers import seed_tx as _seed
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_charts_have_accessible_names(page: Page, live_server, db_path):
    """Канвасы Chart.js невидимы скринридерам без role/aria — проверяем атрибуты."""
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ДИАГРАММА", -10000)
    page.goto(f"{live_server}/dashboard")
    daily = page.locator("#dailyChart")
    expect(daily).to_have_attribute("role", "img")
    expect(daily).to_have_attribute("aria-label", re.compile("по дням"))
    cats = page.locator("#catsChart")
    expect(cats).to_have_attribute("role", "img")
    expect(cats).to_have_attribute("aria-label", re.compile("категориям"))


def test_reduced_motion_disables_transform_transition(page: Page, live_server):
    """При prefers-reduced-motion у кнопок не остаётся transform в transition-property."""
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{live_server}/")
    prop = page.locator("#import").evaluate("el => getComputedStyle(el).transitionProperty")
    assert "transform" not in prop


def test_theme_toggle_light_dark_system(page: Page, live_server):
    """Переключатель темы: light (дефолт) → dark → system; выбор переживает перезагрузку."""
    page.emulate_media(color_scheme="light")
    page.goto(f"{live_server}/")
    html = page.locator("html")
    assert html.get_attribute("data-theme") == "light"
    page.locator("#theme-toggle").click()
    assert html.get_attribute("data-theme") == "dark"
    page.reload()
    assert html.get_attribute("data-theme") == "dark"  # localStorage пережил перезагрузку
    page.locator("#theme-toggle").click()  # → system (при color-scheme: light)
    assert html.get_attribute("data-theme") == "light"
    page.locator("#theme-toggle").click()  # → light
    assert html.get_attribute("data-theme") == "light"


def test_theme_toggle_survives_boost_navigation(page: Page, live_server, db_path):
    """После hx-boost-навигации переключатель продолжает работать (делегирование событий).

    Регрессия 29.09: обработчик вешался на конкретную кнопку, а boost-свап создаёт новую.
    """
    _seed(str(db_path), "2026-09-10", "ЛЕНТА НАВИГАЦИЯ", -10000)
    page.emulate_media(color_scheme="light")
    page.goto(f"{live_server}/")
    page.locator('nav a[href="/dashboard"]').click()
    page.wait_for_selector("#heat-strip", state="attached")
    page.locator("#theme-toggle").click()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.locator("#theme-toggle").click()
    assert page.locator("html").get_attribute("data-theme") == "light"  # system → light


def test_charts_recolor_on_theme_toggle(page: Page, live_server, db_path):
    """Смена темы перекрашивает Chart.js (палитра читается из токенов при отрисовке).

    Регрессия: Chart.js кэширует цвета датасета — без перерисовки на смене темы графики
    остаются в старой палитре (находка дизайн-ревью v2, 29.09).
    Сигнал — цвет тиков (`--fg-muted`): в v2 `--accent-bg` одинаков в обеих темах (кнопочный teal),
    поэтому именно подписи/тики доказывают перерисовку.
    """
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ЦВЕТ", -10000)
    page.goto(f"{live_server}/dashboard")
    page.wait_for_function("() => window.Chart && window.Chart.getChart('dailyChart')")
    before = page.evaluate("() => Chart.getChart('dailyChart').options.scales.y.ticks.color")
    page.locator("#theme-toggle").click()
    page.wait_for_function(
        "(b) => { const c = window.Chart.getChart('dailyChart');"
        " return c && c.options.scales.y.ticks.color !== b; }",
        arg=before, timeout=3000)


def test_sparkline_and_heat_strip_built(page: Page, live_server, db_path):
    """Волна 7: спарклайн в KPI и карта дней строятся из daily-данных."""
    for i, day in enumerate(("2026-09-10", "2026-09-12", "2026-09-15")):
        _seed(str(db_path), day, f"ЛЕНТА КАРТА {i}", -10000 - i * 5000)
    page.goto(f"{live_server}/dashboard")
    cells = page.locator("#heat-strip .heat-cell")
    assert cells.count() >= 28, f"ячеек карты: {cells.count()}"
    pts = page.locator("#spark-expense polyline").get_attribute("points")
    assert pts and len(pts.split()) >= 2, f"спарклайн пуст: {pts!r}"
