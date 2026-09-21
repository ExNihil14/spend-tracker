"""Контраст UI-цветов (WCAG 2.2): бейджи категорий и счётчик очереди — оффлайн.

Источник требований: `D:\\dev\\docs\\machine\\RESEARCH_HELP_FAQ_BEST_PRACTICES.md` §4
(1.4.1 Use of Color, 1.4.3 Contrast Minimum, 1.4.11 Non-text Contrast).
"""
from __future__ import annotations

from spendtrack.colors import (
    BADGE_TEXT_ON_DARK,
    BADGE_TEXT_ON_LIGHT,
    WCAG_TEXT_MIN,
    badge_text_color,
    composite,
    contrast_ratio,
    relative_luminance,
)
from spendtrack.taxonomy import load_taxonomy


def test_relative_luminance_extremes():
    assert relative_luminance("#000000") == 0.0
    assert relative_luminance("#ffffff") == 1.0
    assert relative_luminance(" #fFfFfF ") == 1.0


def test_contrast_ratio_known_values():
    assert round(contrast_ratio("#000000", "#ffffff"), 2) == 21.0
    assert round(contrast_ratio("#ffffff", "#ffffff"), 2) == 1.0
    # симметричность
    assert contrast_ratio("#22c55e", "#020617") == contrast_ratio("#020617", "#22c55e")


def test_badge_text_color_picks_readable_variant():
    # светлый фон → тёмный текст; тёмный (насыщенный) фон → белый
    assert badge_text_color("#22c55e") == BADGE_TEXT_ON_LIGHT
    assert badge_text_color("#475569") == BADGE_TEXT_ON_DARK
    for bg in ("#22c55e", "#64748b", "#dc2626", "#8b5cf6", "#6366f1"):
        assert contrast_ratio(bg, badge_text_color(bg)) >= WCAG_TEXT_MIN


def test_default_taxonomy_badges_pass_aa():
    """Дефолтная палитра taxonomy: текст на каждом бейдже ≥4.5:1 (текущая и после правок)."""
    for category in load_taxonomy().categories:
        ratio = contrast_ratio(category.color, badge_text_color(category.color))
        assert ratio >= WCAG_TEXT_MIN, f"{category.name} ({category.color}): {ratio:.2f}"


def test_queue_counter_badge_passes_aa():
    """Счётчик очереди: amber-300 на bg-amber-500/20 поверх slate-950."""
    background = composite("#f59e0b", "#020617", 0.2)
    assert contrast_ratio("#fcd34d", background) >= WCAG_TEXT_MIN


def test_composite_blends_channels():
    assert composite("#ffffff", "#000000", 0.5) == "#808080"
    assert composite("#ffffff", "#000000", 0.0) == "#000000"
    assert composite("#ffffff", "#000000", 1.0) == "#ffffff"
