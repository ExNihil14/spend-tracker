"""Ребрендинг 29.09: a11y-инварианты графиков и моушена (e2e, офлайн-сервер)."""
from __future__ import annotations

import re
import sqlite3

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


def test_theme_toggle_two_states(page: Page, live_server):
    """Тема — двухпозиционный тоггл (как на opencode.ai): клик → тёмная, ещё клик → светлая; персист; иконка.

    System-режима нет: дефолт — светлая даже при тёмной ОС; легаси-значение 'system' нормализуется в светлую.
    """
    page.emulate_media(color_scheme="dark")  # тёмная ОС не должна менять дефолт (две темы, не system)
    page.goto(f"{live_server}/")
    html = page.locator("html")
    assert html.get_attribute("data-theme") == "light"  # дефолт — светлая
    # иконка показывает ДЕЙСТВИЕ: в светлой — луна («переключить на тёмную»)
    assert page.locator("#theme-toggle .theme-ico-moon").is_visible()
    assert not page.locator("#theme-toggle .theme-ico-sun").is_visible()
    page.locator("#theme-toggle").click()
    assert html.get_attribute("data-theme") == "dark"   # один клик — целевая тема
    assert page.locator("#theme-toggle").get_attribute("aria-pressed") == "true"
    # в тёмной — солнце («переключить на светлую»)
    assert page.locator("#theme-toggle .theme-ico-sun").is_visible()
    assert not page.locator("#theme-toggle .theme-ico-moon").is_visible()
    page.reload()
    assert html.get_attribute("data-theme") == "dark"   # localStorage пережил перезагрузку
    page.locator("#theme-toggle").click()
    assert html.get_attribute("data-theme") == "light"
    assert page.locator("#theme-toggle .theme-ico-moon").is_visible()

    # легаси «system» (до Wave 1.3) — нормализуется в светлую, без авто-следования ОС
    page.evaluate("() => localStorage.setItem('spendtrack-theme', 'system')")
    page.reload()
    assert html.get_attribute("data-theme") == "light"
    assert page.locator("#theme-toggle").get_attribute("aria-pressed") == "false"


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
    assert page.locator("html").get_attribute("data-theme") == "light"


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


def test_heat_strip_has_text_equivalent_per_day(page: Page, live_server, db_path):
    """Карта дней: у графики должен быть текстовый эквивалент по дням (решение 07.10, вариант B).

    Пока по дням нет текста, полоса — единственное представление, и её ячейки обязаны
    сами проходить SC 1.4.11 (≥3:1 к карточке). Замерено вживую: в светлой теме три уровня
    из четырёх ниже порога (1.43 / 1.85 / 2.62), соседние L1↔L2 различимы лишь 1.30.
    С текстовым эквивалентом ячейки становятся supplementary — 1.4.11 к ним не применяется,
    а градиент остаётся читаемым как интенсивность.
    """
    _seed(str(db_path), "2026-09-05", "ТЕКСТ-ПУТЬ A", -10000)   # 100 ₽
    _seed(str(db_path), "2026-09-12", "ТЕКСТ-ПУТЬ B", -30000)   # 300 ₽
    page.goto(f"{live_server}/dashboard?month=2026-09")
    page.wait_for_selector("#heat-days table", timeout=5000)
    txt = page.locator("#heat-days").inner_text()
    for needle in ("05.09", "100,00", "12.09", "300,00"):
        assert needle in txt, f"в текстовом эквиваленте нет {needle!r}: {txt[:400]}"

    # Эквивалент обязан быть в a11y-дереве: скрыт визуально, но НЕ скрыт от скринридера.
    flags = page.evaluate(
        "() => { const el = document.querySelector('#heat-days'); const cs = getComputedStyle(el);"
        " return {hidden: el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true',"
        " display: cs.display, visibility: cs.visibility}; }")
    assert not flags["hidden"], flags
    assert flags["display"] != "none" and flags["visibility"] == "visible", flags

    # И доступен по требованию всем (мышь/зрение), а не только скринридеру.
    toggle = page.locator("#heat-days-toggle")
    expect(toggle).to_have_count(1)
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_have_attribute("aria-controls", "heat-days")
    toggle.click()
    expect(page.locator("#heat-days-toggle")).to_have_attribute("aria-expanded", "true")
    assert "300,00" in page.locator("#heat-days").inner_text()


def test_poster_focus_ring_is_light(page: Page, live_server):
    """Ревью Opus 5 (C1): на градиентном постере кольцо фокуса белое (аква-ринг сливался со стопом).

    Пустая очередь → постер; доходим табом до CTA и проверяем computed outlineColor.
    """
    page.goto(f"{live_server}/approve")
    expect(page.locator("#review-empty .poster")).to_be_visible()
    # Dash 4.6 (#3): прямой фокус вместо хрупкого tab-loop до 40 итераций (ломается при новых
    # фокусируемых элементах до постера); цель теста — computed-цвет кольца, а не порядок табов.
    page.locator("#review-empty .poster a").first.focus()
    assert page.evaluate(
        "() => !!(document.activeElement && document.activeElement.closest('#review-empty .poster'))")
    # transition-colors анимирует и outline-color — ждём конечного значения (иначе читаем промежуточный кадр)
    page.wait_for_function(
        "() => getComputedStyle(document.activeElement).outlineColor === 'rgb(255, 255, 255)'",
        timeout=2000)


def test_poster_cta_reachable_by_keyboard(page: Page, live_server):
    """Astra site_tail 05.10: CTA постера достижим РЕАЛЬНЫМ Tab'ом (страховка от `tabindex="-1"`).

    Прямой `.focus()` в цветовом тесте выше не ловит выпадение CTA из tab-порядка.
    Критерий выхода — полный цикл фокуса (повтор элемента / уход фокуса на body), без произвольного
    лимита нажатий: не встретили CTA за цикл — он выпал из последовательности.
    """
    page.goto(f"{live_server}/approve")
    expect(page.locator("#review-empty .poster")).to_be_visible()
    page.evaluate("() => { window.__tabSeen = new WeakSet(); }")
    reached = False
    for presses in range(1, 400):  # предохранитель от зависания; критерий выхода — цикл, не число
        page.keyboard.press("Tab")
        state = page.evaluate(
            "() => { const el = document.activeElement;"
            " if (!el || el === document.body || el === document.documentElement) return 'body';"
            " if (window.__tabSeen.has(el)) return 'cycle';"
            " window.__tabSeen.add(el);"
            " return el.closest('#review-empty .poster') ? 'poster' : 'other'; }")
        if state == "poster":
            reached = True
            break
        if state in ("cycle", "body") and presses > 1:
            break
    assert reached, "CTA постера выпал из tab-порядка (не достигнут за полный цикл фокуса)"


def test_sticky_nav_reflow_guard(page: Page, live_server):
    """Ревью Opus 5 (C2): анкоры не прячутся под sticky (scroll-padding) + при высоте <500px шапка не sticky."""
    page.goto(f"{live_server}/")
    pad = page.evaluate("() => getComputedStyle(document.documentElement).scrollPaddingTop")
    assert pad not in ("", "auto", "0px"), pad
    page.set_viewport_size({"width": 1280, "height": 480})
    pos = page.evaluate("() => getComputedStyle(document.querySelector('nav')).position")
    assert pos == "static", pos


def test_chart_instances_do_not_leak_on_month_swaps(page: Page, live_server, db_path):
    """Ревью Opus 5 (C6): 6 свапов месяцев — Chart.js-инстансы не копятся (destroy на htmx:beforeSwap)."""
    conn = sqlite3.connect(str(db_path))
    for month, desc, kop in (("2026-04-10", "ЛЕНТА АПР", -4000), ("2026-05-10", "ЛЕНТА МАЙ", -5000),
                             ("2026-06-10", "ЛЕНТА ИЮН", -6000), ("2026-07-10", "ЛЕНТА ИЮЛ", -7000),
                             ("2026-08-10", "ЛЕНТА АВГ", -8000), ("2026-09-10", "ЛЕНТА СЕН", -9000)):
        conn.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
            " confidence, created, updated) VALUES(?,?,?, 'groceries', 'rule', 1.0,"
            " datetime('now'), datetime('now'))", (month, desc, kop))
    conn.commit()
    conn.close()

    page.goto(f"{live_server}/dashboard")
    page.wait_for_function("() => window.Chart && Chart.getChart('dailyChart')")
    # Dash 4.6 (#2): без wait_for_timeout — ждём детерминированно URL месяца И перерисовку чарта
    # (boost-свап: push-url + Chart после beforeSwap/load), иначе тест флакует на медленной машине.
    for month in ("2026-08", "2026-07", "2026-06", "2026-05", "2026-04"):
        page.click('a[aria-label="Предыдущий месяц"]')
        page.wait_for_function(
            "(m) => location.search.includes('month=' + m)"
            " && window.Chart && Chart.getChart('dailyChart')",
            arg=month, timeout=5000)
    page.wait_for_function("() => window.Chart && Chart.getChart('dailyChart')")
    count = page.evaluate("() => Object.keys(window.Chart.instances).length")
    assert count <= 2, f"инстансов Chart.js: {count} (ожидалось ≤2 — по канвасам страницы)"


def test_text_spacing_11412_nav_and_chips(page: Page, live_server, db_path):
    """Ревью (S4): SC 1.4.12 — при letter/word-spacing надбавках nav-пилюли и чипы не обрезаются."""
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ИНТЕРВАЛЫ", -10000)
    page.goto(f"{live_server}/")
    page.evaluate(
        "() => { const set = (el) => { el.style.letterSpacing = '0.12em'; el.style.wordSpacing = '0.16em'; };"
        " document.querySelectorAll('nav, nav a, #tx-table .rounded-full').forEach(set); }")
    overflow = page.evaluate(
        "() => Array.from(document.querySelectorAll('nav, nav a, #tx-table .rounded-full'))"
        ".filter(el => el.scrollWidth > el.clientWidth + 1).length")
    assert overflow == 0, f"обрезанных элементов при text-spacing: {overflow}"


def test_primary_controls_target_size_24(page: Page, live_server):
    """Ревью (S6): ключевые контролы (пилюли, кнопки, селекты, тоггл) ≥24×24 CSS px (SC 2.5.8)."""
    page.goto(f"{live_server}/")
    boxes = page.evaluate(
        "() => Array.from(document.querySelectorAll('nav a.nav-pill, button, select, #theme-toggle'))"
        ".filter(el => el.offsetParent !== null)"
        ".map(el => ({ tag: el.tagName, id: el.id || el.className.toString().slice(0, 30),"
        " w: Math.round(el.getBoundingClientRect().width), h: Math.round(el.getBoundingClientRect().height) }))")
    bad = [b for b in boxes if b["w"] < 24 or b["h"] < 24]
    assert not bad, f"контролы меньше 24×24: {bad}"


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
