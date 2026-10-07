"""Дневной итог ленты: различаем «валютных операций нет» и «про валютные операции неизвестно».

Адъюдикация wave8 (`ui` #1 — замечание к фиксу волны 7): `{% set day_fx_map = day_fx | default({}) %}`
сливает два разных состояния — карту не передали и карту передали, но без записей. В первом случае
шапка дня показывала «итог X» без каких-либо пояснений, хотя валютные операции в этот итог не входят
и наличие их неизвестно: число выглядело полным, а оно неполно. Сегодня оба текущих пути рендера
`day_fx` передают, поэтому дефект латентный — но фолбэк волны 7 существует именно для будущих точек
рендера, значит и пояснение должно быть честным именно там.

Собственное ревью 07.10 (проба не-mapping значений): `default({})` и его волна-8 замена
`is defined` одинаково падают с `UndefinedError`, если `day_fx` передана как `None`, список или
строка — `.get` есть только у mapping. Сегодня таких точек вызова нет, то есть дефект латентный,
но с тем же радиусом поражения, что и исходный: одна такая точка рендера уронит всю страницу (500).
Фолбэк обязан переживать любой вход, который точка рендера может реально передать.

Состояния проверяются по отрендеренному HTML (публичный интерфейс шаблона):
  1) карты нет              → «без учёта валюты» (а НЕ «валютных операций нет»);
  2) карта есть, день пуст → без маркера (итог полный);
  3) карта есть, день с валютными → «+ валюта» и пояснение в title (регресс wave5 S4);
  4) `day_fx` не mapping    → страница рендерится, состояние трактуется как «неизвестно» (1).
"""
from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "bad",
    [None, [], "2026-10", 0],
    ids=["none", "list", "str", "zero"],
)
def test_day_total_survives_non_mapping_fx(bad):
    """`day_fx` передана не-mapping'ом: `.get` недоступен → был UndefinedError (500 на страницу).

    Точка рендера вправе передать `None` (например, «счётчиков нет» вместо «пустой карты») — это
    естественная запись, а не опечатка. Фолбэк обязан трактовать такой вход как «неизвестно»:
    страница рендерится, неполнота итога помечена.
    """
    try:
        html = _render(day_fx=bad)
    except Exception as exc:  # noqa: BLE001 — контракт именно «не падать», тип исключения не важен
        pytest.fail(f"day_fx={bad!r} уронил рендер: {type(exc).__name__}: {exc}")

    assert "2026-10-01" in html, "день не отрендерился"
    assert "без учёта валюты" in html, f"не-mapping воспринят как «валютных нет»: {html[:400]}"
    assert "+ валюта" not in html, "не-mapping не может означать наличие валютных операций"