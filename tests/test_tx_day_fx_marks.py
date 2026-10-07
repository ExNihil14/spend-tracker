"""Дневной итог ленты: различаем «валютных операций нет» и «про валютные операции неизвестно».

Адъюдикация wave8 (`ui` #1 — замечание к фиксу волны 7): `{% set day_fx_map = day_fx | default({}) %}`
сливает два разных состояния — карту не передали и карту передали, но без записей. В первом случае
шапка дня показывала «итог X» без каких-либо пояснений, хотя валютные операции в этот итог не входят
и наличие их неизвестно: число выглядело полным, а оно неполно. Сегодня оба текущих пути рендера
`day_fx` передают, поэтому дефект латентный — но фолбэк волны 7 существует именно для будущих точек
рендера, значит и пояснение должно быть честным именно там.

Три состояния проверяются по отрендеренному HTML (публичный интерфейс шаблона):
  1) карты нет              → «без учёта валюты» (а НЕ «валютных операций нет»);
  2) карта есть, день пуст → без маркера (итог полный);
  3) карта есть, день с валютными → «+ валюта» и пояснение в title (регресс wave5 S4).
"""
from __future__ import annotations

from spendtrack.routers.frontend import templates

TX_ROW = {
    "id": 1,
    "date": "2026-10-01",
    "description": "ЛЕНТА",
    "category": "groceries",
    "amount_kopecks": -1000,
    "currency": "RUB",
    "category_source": "rule",
    "merchant": "",
    "confidence": 1.0,
}

BASE = {
    "transactions": [dict(TX_ROW)],
    "day_totals": {"2026-10-01": -1000},
    "group_days": True,
    "current": "2026-10",
    "cat_colors": {},
    "catname": lambda s: s,
    "fmt_date": lambda d: d,
    "fmt_month": lambda m: m,
    "fmt_money": lambda k, cur=None: str(k),
}


def _render(**extra) -> str:
    ctx = dict(BASE)
    ctx.update(extra)
    return templates.get_template("partials/tx_rows.html").render(**ctx)


def test_day_total_marked_when_fx_map_absent():
    """Карту не передали → итог может быть неполным, и это надо сказать."""
    html = _render()

    assert "2026-10-01" in html, "день вообще не отрендерился"
    assert "без учёта валюты" in html, f"неполнота итога не обозначена: {html[:400]}"
    assert "+ валюта" not in html, "при отсутствии карты нельзя утверждать, что валюта есть"


def test_day_total_plain_when_fx_map_has_no_entry():
    """Карта передана и на день валютных операций нет → итог полный, маркер не нужен."""
    html = _render(day_fx={})

    assert "2026-10-01" in html
    assert "без учёта валюты" not in html, html[:400]
    assert "+ валюта" not in html, html[:400]


def test_day_total_marks_currency_when_fx_map_has_entry():
    """Карта передана и валютные операции были → «+ валюта» и пояснение (регресс wave5 S4)."""
    html = _render(day_fx={"2026-10-01": 2})

    assert "+ валюта" in html, html[:400]
    assert "Операции в валюте в итог не входят" in html, html[:400]
    assert "без учёта валюты" not in html, "на одном дне две взаимоисключающие пометки"
