"""Контрасты токенов (WCAG 2.2 AA) в ОБЕИХ темах: палитра не должна «поехать» при ребрендинге.

Пороги и формула — из RESEARCH_REBRANDING_2026-09-29.md §1.3:
SC 1.4.3 (текст ≥4.5:1), SC 1.4.11 (UI/графика/фокус ≥3:1), SC 1.4.1 (не только цвет).
Расчёт — relative luminance (sRGB), без округления: 4.499 — не проходит.
Светлая тема — базовый `:root`; тёмная — блок `:root[data-theme="dark"]` (ставит static/theme.js).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "src" / "spendtrack" / "tokens.css"
DARK_MARKER = ':root[data-theme="dark"]'

# (foreground, background, минимум): 4.5 — текст, 3.0 — UI/графика/фокус
PAIRS: list[tuple[str, str, float]] = [
    ("fg", "canvas", 4.5), ("fg", "surface", 4.5), ("fg", "surface-2", 4.5),
    ("fg-strong", "surface", 4.5),
    ("fg-muted", "canvas", 4.5), ("fg-muted", "surface", 4.5),
    ("fg-subtle", "surface", 4.5),
    ("accent", "canvas", 4.5), ("accent", "surface", 4.5), ("accent-hover", "surface", 4.5),
    ("on-accent", "accent-bg", 4.5), ("on-accent", "accent-bg-hover", 4.5),
    ("income", "surface", 4.5), ("warn", "surface", 4.5), ("danger", "surface", 4.5),
    ("focus-ring", "canvas", 3.0), ("focus-ring", "surface", 3.0),
    ("accent", "canvas", 3.0), ("income", "canvas", 3.0), ("warn", "canvas", 3.0),
    ("danger", "canvas", 3.0), ("accent-bg", "canvas", 3.0), ("danger-bg", "canvas", 3.0),
    # v2 «Стикербук» (29.09, Приложение B DESIGN_DIRECTION_V2): soft-чипы вместо alpha,
    # границы полей ≥3:1 (best practice 1.4.11), акцент ИИ (--accent-2) и info-роль
    ("accent", "accent-soft", 4.5), ("accent-2", "accent-2-soft", 4.5),
    ("info", "info-soft", 4.5), ("income", "income-soft", 4.5),
    ("warn", "warn-soft", 4.5), ("danger", "danger-soft", 4.5),
    ("accent-2", "surface", 4.5), ("info", "surface", 4.5),
    ("on-accent", "accent-2-bg", 4.5),
    ("line-strong", "canvas", 3.0), ("line-strong", "surface", 3.0),
    # Ревью Opus 5 (30.09): границы контролов живут и на surface-2/-3 (поля в панелях, quiet-кнопки
    # с hover:bg-surface-3) — пары расширены, токен затемнён/высветлен до ≥3:1 во всех контекстах
    ("line-strong", "surface-2", 3.0), ("line-strong", "surface-3", 3.0),
    ("fg", "surface-3", 4.5), ("fg-muted", "surface-2", 4.5), ("fg-subtle", "canvas", 4.5),
    ("focus-ring", "surface-3", 3.0),
    # Wave 1: постер (белый текст на посчитанных стопах §3.5) и hover-фон кнопок-пилюль постера
    ("on-accent", "grad-from", 4.5), ("on-accent", "grad-to", 4.5),
    ("accent", "surface-2", 4.5),
]


def _vars(css: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"--([\w-]+):\s*([^;]+);", css)}


def _themes() -> dict[str, dict[str, str]]:
    css = TOKENS.read_text(encoding="utf-8")
    assert DARK_MARKER in css, "нет блока тёмной темы [data-theme=dark]"
    head, tail = css.split(DARK_MARKER, 1)
    light = _vars(head)
    dark = {**light, **_vars(tail.split("}", 1)[0])}
    return {"light": light, "dark": dark}


def _resolve(vars_: dict[str, str], name: str) -> str:
    value = vars_[name]
    ref = re.fullmatch(r"var\(--([\w-]+)\)", value)
    if ref:
        return _resolve(vars_, ref.group(1))
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), f"--{name}: ожидался hex, получено {value!r}"
    return value.lower()


def _luminance(hex6: str) -> float:
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _ratio(a: str, b: str) -> float:
    l1, l2 = _luminance(a), _luminance(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def test_tokens_contrast_wcag_aa_both_themes() -> None:
    themes = _themes()
    for theme, vars_ in themes.items():
        for name in ("focus-ring", "surface-3"):
            assert name in vars_, f"[{theme}] токен --{name} отсутствует"
        fails = []
        for fg, bg, need in PAIRS:
            ratio = _ratio(_resolve(vars_, fg), _resolve(vars_, bg))
            if ratio < need:
                fails.append(f"{fg} на {bg}: {ratio:.2f} < {need}")
        assert not fails, f"[{theme}] контрасты ниже порога: " + "; ".join(fails)
