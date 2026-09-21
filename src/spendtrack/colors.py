"""Контраст и цвета UI (WCAG 2.2: 1.4.1/1.4.3/1.4.11).

Централизованные хелперы для шаблонов: цвет не должен быть единственным носителем смысла,
а текст на цветном бейдже — читаться (≥4.5:1). Дефолтная палитра taxonomy проверяется тестом.
"""
from __future__ import annotations

BADGE_TEXT_ON_LIGHT = "#020617"   # slate-950
BADGE_TEXT_ON_DARK = "#ffffff"

WCAG_TEXT_MIN = 4.5               # AA для обычного текста
WCAG_NONTEXT_MIN = 3.0            # AA для крупного текста/границ/иконок


def _srgb_channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """Относительная яркость WCAG для `#rrggbb` (0 — чёрный, 1 — белый)."""
    hex_color = color.strip().lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"ожидается #rrggbb, получено {color!r}")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def contrast_ratio(color_a: str, color_b: str) -> float:
    """Коэффициент контраста двух цветов (1.0 … 21.0)."""
    lum_a, lum_b = relative_luminance(color_a), relative_luminance(color_b)
    hi, lo = max(lum_a, lum_b), min(lum_a, lum_b)
    return (hi + 0.05) / (lo + 0.05)


def badge_text_color(background: str) -> str:
    """Цвет текста для цветного бейджа: выбирается вариант с контрастом ≥4.5:1.

    Для тёмных фонов — белый, для светлых — slate-950. Применяется к палитре категорий,
    которую пользователь может менять в /settings, поэтому выбор считается, а не берётся
    из списка исключений (research §4: «тяжёлым» цветам — белый текст).
    """
    return (BADGE_TEXT_ON_DARK
            if contrast_ratio(background, BADGE_TEXT_ON_DARK)
            > contrast_ratio(background, BADGE_TEXT_ON_LIGHT)
            else BADGE_TEXT_ON_LIGHT)


def composite(foreground: str, background: str, alpha: float) -> str:
    """Наложение полупрозрачного цвета (для проверки контраста полупрозрачных фонов)."""
    fg = foreground.strip().lstrip("#")
    bg = background.strip().lstrip("#")
    mixed = [
        round(int(fg[i:i + 2], 16) * alpha + int(bg[i:i + 2], 16) * (1 - alpha))
        for i in (0, 2, 4)
    ]
    return f"#{mixed[0]:02x}{mixed[1]:02x}{mixed[2]:02x}"
