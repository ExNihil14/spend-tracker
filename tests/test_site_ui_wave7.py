"""Волна site_ui (fb_ui_a/b/c, окно 07.10) — регрессы на подтверждённые находки.

Контекст адъюдикации: оба «critical» ревью (мёртвый `file_hash`-хук и `urlencode` в CSS-селекторах)
ОПРОВЕРГНУТЫ фактами (htmx 2.0.4 в браузере: `hasOwnProperty` → true; `validate_name` допускает только
ASCII-слаги) — здесь защищаем то, что реально подтвердилось: раскладка формы цели, подсказка формата
месяца, честное поведение без JS и живучесть ленты при отсутствующем day_fx.

Тесты — на публичный интерфейс (HTML-ответы роутов + рендер шаблона), не на внутренние структуры.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.routers.frontend import templates

SRC = Path(__file__).resolve().parents[1] / "src" / "spendtrack"
TEMPLATES = SRC / "templates"

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


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "site-ui.db"))
    return TestClient(app)


def test_goals_create_form_grid_survives_narrow_viewport(client):
    """fb_b S1: `sm:grid-cols-[1fr_11rem_10rem_auto]` — трек 1fr имеет авто-минимум (min-content
    поля ввода ~200px), поэтому на 640–700px сумма треков шире вьюпорта и страница уезжает вправо.

    Фикс: `min-w-0` на grid-элементах формы (или `minmax(0,1fr)` в треке).
    """
    page = client.get("/goals").text
    form = page[page.index('hx-post="/api/goals"'):]
    form = form[:form.index("</form>")]
    labels = re.findall(r"<label[^>]*>", form)
    assert labels, "форма создания цели должна иметь <label>-ы"
    assert all("min-w-0" in lb for lb in labels), f"у grid-элементов формы нет min-w-0: {labels}"


def test_due_month_input_documents_format_for_browsers_without_picker(client):
    """fb_b S2: Firefox (десктоп/Android) и Safari на macOS не поддерживают `type=month` —
    поле превращается в текст без подсказки, пользователь пишет «май 2026» и получает 400/тишину."""
    page = client.get("/goals").text
    field = re.search(r"<input[^>]*name=\"due_month\"[^>]*>", page)
    assert field, "поле срока не найдено"
    tag = field.group(0)
    assert 'placeholder="2026-05"' in tag, "нет подсказки формата ГГГГ-ММ"
    assert "pattern=" in tag, "нет маски ввода — браузер без пикера примет мусор"
    assert 'title="Формат' in tag, "нет title с пояснением формата"


def test_goals_page_explains_that_forms_need_javascript(client):
    """fb_b S3: страница целиком htmx-овая; без JS формы без action/method уйдут GET'ом на /goals —
    страница перерисуется, цель не создастся, а пользователь решит, что «что-то произошло»."""
    page = client.get("/goals").text
    assert "<noscript>" in page, "/goals без noscript: без JS форма молча ничего не делает"
    block = page[page.index("<noscript>"):]
    block = block[:block.index("</noscript>")]
    assert "JavaScript" in block or "javascript" in block, "в noscript нет объяснения"


def test_tx_rows_render_when_day_fx_missing_from_context():
    """fb_c S2: `{% set day_fx_count = day_fx.get(t.date) %}` падал UndefinedError, если контекст
    рендера не передал day_fx. Сегодня оба пути (страница и htmx-партиал) его передают, поэтому
    это латентный 500: любая новая точка рендера ленты уронила бы всю страницу.

    Контекст собран как у роута, но БЕЗ day_fx — контракт «шаблон не падает от необязательного ключа»
    (как `has_any | default(true)` в этом же партиале).
    """
    html = templates.get_template("partials/tx_rows.html").render(
        transactions=[dict(TX_ROW)],
        day_totals={"2026-10-01": -1000},
        group_days=True,
        current="2026-10",
        cat_colors={},
        catname=lambda s: s,
        fmt_date=lambda d: d,
        fmt_month=lambda m: m,
        fmt_money=lambda k, cur=None: str(k),
    )
    assert "2026-10-01" in html


def test_templates_avoid_eval_dependent_htmx_attributes():
    """fb_a S4: конфиг htmx выставляет allowEval:false, поэтому `hx-on:*`, `hx-vals='js:…'`,
    `hx-headers='js:…'` и фильтры `hx-trigger="…[expr]"` молча не работают (только запись в консоли).

    Сейчас таких атрибутов нет — тест закрывает весь класс «невидимых» регрессий при правках шаблонов.
    """
    bad = re.compile(r"hx-on[:=]|hx-vals\s*=\s*['\"]js:|hx-headers\s*=\s*['\"]js:|hx-trigger=\"[^\"]*\[")
    offenders: list[str] = []
    for path in TEMPLATES.rglob("*.html"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("{#", "{%")):
                continue  # комментарии/блоки Jinja не рендерятся в атрибуты
            if bad.search(stripped):
                offenders.append(f"{path.name}: {stripped[:90]}")
    assert not offenders, "eval-зависимые htmx-атрибуты при allowEval:false:\n" + "\n".join(offenders)