"""Wave 1 «Стикербук» в браузере: компоновка (бенто/пилюли/постеры) и микро-моушен.

Здесь — только то, что видно в реальном CSS (computed-стили, геометрия); контрасты обеих тем —
unit-тест tests/test_tokens_contrast.py (включая стопы градиента постера).
"""
from __future__ import annotations

import pytest
from helpers import seed_tx as _seed
from playwright.sync_api import Page, expect

from spendtrack.store import Store

pytestmark = pytest.mark.e2e


def _css_var_rgb(page: Page, name: str) -> str:
    """Цвет токена в rgb() так, как его видит браузер (через пробный элемент, без хардкода hex)."""
    return page.evaluate(
        """(name) => {
             const probe = document.createElement('span');
             probe.style.color = 'var(' + name + ')';
             document.body.appendChild(probe);
             const val = getComputedStyle(probe).color;
             probe.remove();
             return val;
           }""", name)


def test_kpi_bento_primary_spans_two_columns(page: Page, live_server, db_path):
    """Primary-плитка (баланс) вдвое шире tint-плиток; суммы 30/24 px, tint — семантические soft-токены."""
    _seed(str(db_path), "2026-09-10", "ЗАРПЛАТА БЕНТО", 500_000)
    _seed(str(db_path), "2026-09-11", "ЛЕНТА БЕНТО", -12345)

    page.goto(f"{live_server}/dashboard")
    primary = page.locator("#kpi-balance")
    expect(primary).to_be_visible()
    income = page.locator("#kpi-balance ~ .bg-income-soft").first
    expense = page.locator("#kpi-balance ~ .bg-accent-soft").first

    ratio = primary.bounding_box()["width"] / income.bounding_box()["width"]
    assert 1.9 <= ratio <= 2.2, f"primary не занимает 2 колонки: ratio={ratio:.2f}"

    size_primary = primary.locator(".tabular-nums").first.evaluate("el => getComputedStyle(el).fontSize")
    size_income = income.locator(".tabular-nums").first.evaluate("el => getComputedStyle(el).fontSize")
    assert size_primary == "30px" and size_income == "24px"

    assert income.evaluate("el => getComputedStyle(el).backgroundColor") == _css_var_rgb(page, "--income-soft")
    assert expense.evaluate("el => getComputedStyle(el).backgroundColor") == _css_var_rgb(page, "--accent-soft")


def test_nav_pills_active_and_sticky(page: Page, live_server):
    """Nav: sticky-пилюли; активная — bg-accent-soft/text-accent + aria-current (не только цвет — форма)."""
    page.goto(f"{live_server}/dashboard")
    nav = page.locator("nav").first
    assert nav.evaluate("el => getComputedStyle(el).position") == "sticky"

    active = page.locator('nav a.nav-pill[aria-current="page"]')
    expect(active).to_have_count(1)
    expect(active).to_have_text("Дашборд")
    assert active.evaluate("el => getComputedStyle(el).backgroundColor") == _css_var_rgb(page, "--accent-soft")
    assert active.evaluate("el => getComputedStyle(el).color") == _css_var_rgb(page, "--accent")
    assert active.evaluate("el => getComputedStyle(el).borderTopLeftRadius") != "0px"

    inactive = page.locator('nav a.nav-pill', has_text="Помощь")
    assert inactive.get_attribute("aria-current") is None


def test_queue_empty_poster_renders_with_light_text(page: Page, live_server):
    """Пустая очередь: постер с градиентом; текст/кнопка — на посчитанных токенах (белый ≥5.36:1)."""
    page.goto(f"{live_server}/approve")
    poster = page.locator("#review-empty .poster")
    expect(poster).to_be_visible()
    bg_image = poster.evaluate("el => getComputedStyle(el).backgroundImage")
    assert bg_image.startswith("linear-gradient"), bg_image
    assert poster.evaluate("el => getComputedStyle(el).color") == _css_var_rgb(page, "--on-accent")

    cta = poster.locator("a", has_text="Как работает очередь")
    expect(cta).to_be_visible()
    assert cta.evaluate("el => getComputedStyle(el).backgroundColor") == _css_var_rgb(page, "--surface")
    assert cta.evaluate("el => getComputedStyle(el).color") == _css_var_rgb(page, "--accent")


def test_counter_chip_pop_and_reduced_motion(page: Page, live_server):
    """«Поп» счётчика очереди: spring-переход по transform; при reduced-motion — выключен."""
    page.goto(f"{live_server}/")
    chip = page.locator("#pending-count")
    assert "transform" in chip.evaluate("el => getComputedStyle(el).transitionProperty")

    page.emulate_media(reduced_motion="reduce")
    page.reload()
    prop = page.locator("#pending-count").evaluate("el => getComputedStyle(el).transitionProperty")
    assert "transform" not in prop, prop


def test_rows_avatar_cascade_and_reduced_motion(page: Page, live_server, db_path):
    """Строки «Расходов»: аватар-иконка отрисован (внешний спрайт), каскад выключается reduced-motion."""
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ДЕКОР", -12345)
    page.goto(f"{live_server}/")
    expect(page.locator(".tx-avatar").first).to_be_visible()
    w, h = page.locator(".tx-avatar use").first.evaluate(
        "el => { const b = el.getBBox(); return [b.width, b.height]; }")
    assert w > 3 and h > 3, "иконка аватара не отрисована"
    page.emulate_media(reduced_motion="reduce")
    page.reload()
    anim = page.locator(".tx-row").first.evaluate("el => getComputedStyle(el).animationName")
    assert anim == "none", anim


def test_budget_percent_countup_keeps_percent_suffix(page: Page, live_server, db_path):
    """Count-up целых процентов бюджета: финальное значение с «%»; деньги клиентом не анимируются."""
    store = Store(db_path=db_path)
    try:
        store.set_budget("groceries", 200_000)  # 2 000 ₽
    finally:
        store.close()
    _seed(str(db_path), "2026-09-10", "ЛЕНТА ПРОЦЕНТ", -100_000)  # 1 000 ₽ → 50%

    page.goto(f"{live_server}/dashboard")
    expect(page.locator("[data-countup]")).to_have_count(1)
    page.wait_for_function(
        "() => { const el = document.querySelector('[data-countup]');"
        " return el && el.textContent.trim() === '50%'; }", timeout=3000)
    assert page.locator("[data-countup-suffix]").count() == 1
