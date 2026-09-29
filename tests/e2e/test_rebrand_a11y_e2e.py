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


def test_charts_have_themed_tooltips_and_hover(page: Page, live_server, db_path):
    """Wave 1-preview: тултипы в токенах, hover-кромка баров, hover-смещение секторов пончика.

    Canvas-графики не имеют DOM — проверяем разрешённую конфигурацию Chart.js (тот же приём,
    что в тестах перекраски/данных).
    """
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ИНТЕРАКТИВ", -10000)
    page.goto(f"{live_server}/dashboard")
    page.wait_for_function(
        "() => window.Chart && window.Chart.getChart('dailyChart') && window.Chart.getChart('catsChart')")
    cfg = page.evaluate(
        "() => {"
        " const d = Chart.getChart('dailyChart'); const c = Chart.getChart('catsChart');"
        " const surface = getComputedStyle(document.documentElement).getPropertyValue('--surface').trim();"
        " return { tooltipBg: d.options.plugins.tooltip.backgroundColor,"
        "          hoverBorder: d.data.datasets[0].hoverBorderColor,"
        "          hoverOffset: c.data.datasets[0].hoverOffset,"
        "          donutBorder: c.data.datasets[0].borderColor,"
        "          surface: surface }; }")

    assert cfg["tooltipBg"], "тултип без токен-фона"
    assert cfg["hoverBorder"], "нет hover-кромки баров"
    assert cfg["hoverOffset"] and cfg["hoverOffset"] > 0, "пончик без hover-смещения"
    assert str(cfg["donutBorder"]).lower() == cfg["surface"].lower(), "граница секторов не по --surface"


def test_sparkline_and_heat_strip_built(page: Page, live_server, db_path):
    """Волна 7: спарклайн в KPI и карта дней строятся из daily-данных."""
    for i, day in enumerate(("2026-09-10", "2026-09-12", "2026-09-15")):
        _seed(str(db_path), day, f"ЛЕНТА КАРТА {i}", -10000 - i * 5000)
    page.goto(f"{live_server}/dashboard")
    cells = page.locator("#heat-strip .heat-cell")
    assert cells.count() >= 28, f"ячеек карты: {cells.count()}"
    line_d = page.locator("#spark-expense path.spark-line").get_attribute("d")
    assert line_d and "C" in line_d, f"спарклайн не сглажен (нет кривых): {line_d!r}"
    area_d = page.locator("#spark-expense path.spark-area").get_attribute("d")
    assert area_d and area_d.endswith("Z"), f"area-заливка не построена: {area_d!r}"
    box = page.locator("#spark-expense path.spark-line").bounding_box()
    assert box and box["height"] > 5, f"спарклайн не показывает динамику: {box}"


def test_doughnut_click_opens_filtered_list(page: Page, live_server, db_path):
    """Пончик: cursor над сектором и легендой; клик по категории — тоггл; по сектору — список."""
    _seed(str(db_path), "2026-09-10", "ЛЕНТА КЛИК", -10000)
    page.goto(f"{live_server}/dashboard")
    page.wait_for_function(
        "() => { const c = window.Chart && Chart.getChart('catsChart');"
        " return c && c.getDatasetMeta(0).data.length > 0 && c.legend"
        " && c.legend.legendHitBoxes && c.legend.legendHitBoxes.length; }")

    # 1) hover по сектору → pointer (курсор предварительно уводим, чтобы не поймать «инерцию»)
    point = page.evaluate(
        """() => {
             const c = Chart.getChart('catsChart');
             const el = c.getDatasetMeta(0).data[0];
             const mid = (el.startAngle + el.endAngle) / 2;
             const r = (el.innerRadius + el.outerRadius) / 2;
             const box = document.getElementById('catsChart').getBoundingClientRect();
             return { x: box.x + el.x + Math.cos(mid) * r, y: box.y + el.y + Math.sin(mid) * r };
           }""")
    page.mouse.move(5, 5)
    page.mouse.move(point["x"], point["y"])
    cursor = page.evaluate("() => getComputedStyle(document.getElementById('catsChart')).cursor")
    assert cursor == "pointer", f"курсор над сектором: {cursor!r}"

    # 2) hover по элементу легенды → pointer (легенда кликабельна — это неочевидно, курсор обязателен)
    legend_point = page.evaluate(
        """() => {
             const c = Chart.getChart('catsChart');
             const b = c.legend.legendHitBoxes[0];
             const box = document.getElementById('catsChart').getBoundingClientRect();
             return { x: box.x + b.left + b.width / 2, y: box.y + b.top + b.height / 2 };
           }""")
    page.mouse.move(5, 5)
    page.mouse.move(legend_point["x"], legend_point["y"])
    cursor2 = page.evaluate("() => getComputedStyle(document.getElementById('catsChart')).cursor")
    assert cursor2 == "pointer", f"курсор над легендой: {cursor2!r}"

    # 3) клик по категории скрывает сектор, повторный — возвращает
    page.mouse.click(legend_point["x"], legend_point["y"])
    page.wait_for_function("() => Chart.getChart('catsChart').getDataVisibility(0) === false")
    page.mouse.click(legend_point["x"], legend_point["y"])
    page.wait_for_function("() => Chart.getChart('catsChart').getDataVisibility(0) === true")

    # 4) клик по сектору → список с фильтром категории
    page.mouse.click(point["x"], point["y"])
    page.wait_for_url(lambda url: "category=" in url, timeout=5000)
    assert "category=groceries" in page.url, page.url
