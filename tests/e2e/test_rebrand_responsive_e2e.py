"""Ребрендинг 29.09: адаптивность (матрица вьюпортов) и новые элементы (бюджет-бары)."""
from __future__ import annotations

import pytest
from helpers import seed_smoke_data
from playwright.sync_api import Page

from spendtrack.store import Store

pytestmark = pytest.mark.e2e

PAGES = ("/", "/dashboard", "/approve", "/settings")
VIEWPORTS = (375, 768, 1280)


@pytest.fixture(autouse=True)
def _seeded(db_path) -> None:
    seed_smoke_data(db_path)


@pytest.mark.parametrize("width", VIEWPORTS)
@pytest.mark.parametrize("path", PAGES)
def test_no_horizontal_overflow_viewport_matrix(page: Page, live_server: str, path: str,
                                                width: int) -> None:
    """Адаптивность: на 375/768/1280 нет горизонтального скролла документа (WCAG 1.4.10)."""
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(live_server + path, wait_until="load")
    overflow = page.evaluate(
        "() => { const el = document.scrollingElement; return el.scrollWidth - el.clientWidth; }")
    assert overflow <= 0, f"{path} @{width}px: горизонтальный скролл +{overflow}px"


def test_nav_reachable_on_mobile(page: Page, live_server: str) -> None:
    """На 375px все пункты навигации видимы (nav переносится, не обрезается)."""
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(live_server + "/", wait_until="load")
    links = page.locator("nav a")
    count = links.count()
    assert count >= 5, f"пунктов nav: {count}"
    for i in range(count):
        assert links.nth(i).is_visible(), f"пункт nav #{i} не виден на 375px"


def test_budget_bar_uses_transform_scale(page: Page, live_server: str, db_path) -> None:
    """Новые бюджет-бары анимируются transform: scaleX(--p/100), а не width (INP/layout)."""
    store = Store(db_path=db_path)
    try:
        store.set_budget("groceries", 2_000_000)  # 20 000 ₽; расходы смоука ≈ 750 ₽ → --p ≈ 4
    finally:
        store.close()
    page.goto(live_server + "/dashboard", wait_until="load")
    assert page.locator(".budget-bar").count() >= 1, "бюджет-бар не отрисован"
    info = page.locator(".budget-bar").first.evaluate(
        "el => ({ t: getComputedStyle(el).transform, p: el.style.getPropertyValue('--p') })")
    assert info["t"].startswith("matrix"), f"transform не применён: {info['t']!r}"
    scale = float(info["t"].split("(")[1].split(",")[0])
    assert 0 < scale <= 1.0, f"scaleX={scale} при --p={info['p']!r}"
