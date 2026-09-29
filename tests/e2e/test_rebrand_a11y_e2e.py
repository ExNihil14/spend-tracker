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
