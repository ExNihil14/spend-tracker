"""P2 UX-полировка: обучающие пустые состояния, микро-подсказки, знаки сумм (оффлайн, TestClient).

DoD POLISH_PLAN #7-#9: тексты по `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` (§4, §6),
знак суммы — не только цветом (WCAG 1.4.1), ссылки ведут на существующие якоря /help.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.store import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "ui.db"))
    return TestClient(app)


def _add(client: TestClient, amount: str, desc: str = "ЛЕНТА", date: str = "2026-09-12"):
    r = client.post("/api/transactions", json={"date": date, "description": desc, "amount": amount})
    assert r.status_code == 200


def test_empty_list_teaches_first_step(client):
    html = client.get("/").text
    assert "Пока нет транзакций" in html
    assert 'href="/help#faq-import-sber"' in html


def test_first_run_checklist_shows_four_steps(client):
    """P2 #10: на первом запуске главная показывает чек-лист 4 шагов со ссылками на действия."""
    html = client.get("/").text
    assert 'id="start-checklist"' in html
    assert "Первый запуск — 4 шага" in html
    for href in ('href="#import"', 'href="#add"', 'href="/approve"', 'href="/settings"',
                 'href="/dashboard"', 'href="/help#quick-start"'):
        assert href in html, href


def test_first_run_checklist_hidden_after_import(client, tmp_path):
    store = Store(db_path=tmp_path / "ui.db")
    assert store.batch_count() == 0
    store.add_batch("sber.csv", "sha", 1)
    assert store.batch_count() == 1
    store.close()
    assert 'id="start-checklist"' not in client.get("/").text


def test_first_run_checklist_hidden_after_manual_add(client):
    _add(client, "-10.00")
    assert 'id="start-checklist"' not in client.get("/").text


def test_empty_queue_hint_links_to_help(client):
    html = client.get("/approve").text
    assert "Все подтверждены" in html
    assert 'href="/help#faq-queue-why"' in html


def test_dashboard_onboarding_when_no_data(client):
    html = client.get("/dashboard").text
    assert 'id="onboarding"' in html
    assert 'href="/#import"' in html and 'href="/approve"' in html
    assert 'href="/help#quick-start"' in html
    assert "Расходы по дням" not in html  # вместо пустых графиков — онбординг


def test_amounts_render_with_explicit_signs_and_adaptive_badges(client):
    _add(client, "-1234.56", "ЛЕНТА")
    _add(client, "250000.00", "ЗАРАБОТНАЯ ПЛАТА")
    html = client.get("/").text
    assert "\u22121\u00a0234,56 ₽" in html   # U+2212, разряды NBSP, запятая, ₽
    assert "+250\u00a0000,00 ₽" in html      # явный плюс у дохода
    assert "background:#22c55e;color:#020617" in html  # светлый бейдж groceries → тёмный текст


def test_category_links_keep_month_and_full_navigation(client):
    """Клик по бейджу: полная навигация (hx-boost=false) + месяц в href (баг смоука 23.09).

    Иначе htmx наследует target/select/swap от #tx-table и подменяет только таблицу
    (шапка/итоги/фильтр остаются от прошлого состояния), а без месяца уводит в последний месяц.
    """
    _add(client, "-100.00", "ЛЕНТА")  # groceries, 2026-09-12
    html = client.get("/?month=2026-09").text
    # S5 (Astra 02.10): hx-boost="false" должен стоять именно на бейдже категории — иначе любой
    # другой элемент с этим атрибутом удовлетворял проверку, а регрессия оставалась незамеченной.
    assert re.search(
        r'<a\b[^>]*href="/\?month=2026-09&(?:amp;)?category=groceries"[^>]*hx-boost="false"'
        r'|<a\b[^>]*hx-boost="false"[^>]*href="/\?month=2026-09&(?:amp;)?category=groceries"', html)
    assert ">Продукты</option>" in html  # фильтр-селект — RU-имена, не слаги


def test_noscript_notices(client):
    """O10 (Astra 02.10): без JS страницы настроек/дашборда объясняют ограничение (htmx-only by design)."""
    assert "<noscript" in client.get("/settings").text
    assert "<noscript" in client.get("/dashboard").text


def test_htmx_config_meta_precedes_script(client):
    """C1 (Astra 02.10): meta htmx-config — ДО htmx.min.js, иначе allowEval/historyCacheSize не применяются."""
    html = client.get("/").text
    assert html.index('name="htmx-config"') < html.index("htmx.min.js")


def test_async_sinks_are_live_regions(client):
    """#importmsg/#newmsg — role=status aria-live: результаты импорта/добавления озвучиваются (WCAG 4.1.3)."""
    html = client.get("/").text
    assert 'id="importmsg" role="status" aria-live="polite"' in html
    assert 'id="newmsg" role="status" aria-live="polite"' in html


def test_help_links_disable_boost(client):
    """Ссылки /help#... не бустятся: иначе фрагмент не применяется и пользователь видит верх /help."""
    assert '/help#faq-import-sber" hx-boost="false"' in client.get("/").text
    assert '/help#faq-queue-why" hx-boost="false"' in client.get("/approve").text


def test_filters_swap_table_with_oob_actions(client):
    """Wave6 feed S1/S2: фильтры свапают только #tx-table (+OOB #tx-actions) — фокус/каретка и открытые
    панели выживают; шапка («✕»/экспорт) обновляется OOB; month — скрытым полем (иначе смена фильтра
    уводила на месяц последней операции)."""
    html = client.get("/").text
    assert 'id="tx-card"' in html and 'id="tx-actions"' in html
    assert html.count('hx-select="#tx-table"') >= 5  # форма + 2 селекта + поиск + refresh-list
    assert html.count('hx-select-oob="#tx-actions:outerHTML"') == 4
    assert 'hx-select="#tx-card"' not in html  # карточка больше не цель свапа фильтров
    assert 'name="month" value=' in html


def test_fx_only_day_is_labeled_not_zero(client):
    """День только с валютными операциями — «только в валюте», а не ложный «итог 0,00 ₽»."""
    r = client.post("/api/transactions", json={"date": "2026-09-12", "description": "USD КОФЕ",
                                               "amount": "-10.00", "currency": "USD"})
    assert r.status_code == 200
    html = client.get("/?month=2026-09").text
    assert "только в валюте" in html


def test_dashboard_heatmap_counts_spend_not_signed_total():
    """C1 (Astra 02.10): карта дней считает РАСХОДЫ (max(0, -total_k)) — статический гард по JS.

    Регрессия (знаковый total_k) делала все ячейки level 0 и «максимум 0 ₽» в aria-label;
    JS не покрыт unit-тестами, поэтому держим дешёвый контракт-гард на исходник.
    """
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "src" / "spendtrack" / "static" / "dashboard.js").read_text(
        encoding="utf-8")
    heat = js[js.index("function drawHeat"):]
    heat = heat[:heat.index("\n  }")]
    assert "Math.max(0, -d.total_k)" in heat
    assert "d.total_k > max" not in heat  # старый знаковый максимум


def test_error_banner_hooks_present():
    """W1 ресёрча ошибок: htmx-ошибки и сетевые сбои показываются пользователю (стат-гард)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "spendtrack"
    js = (root / "static" / "app.js").read_text(encoding="utf-8")
    assert "htmx:responseError" in js and "htmx:sendError" in js
    base = (root / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'id="error-banner"' in base and 'role="alert"' in base


def test_untrusted_description_is_escaped_everywhere(client):
    """S6 (Astra 02.10): описание из выписки — недоверенный ввод; на страницах не должно быть
    исполняемых фрагментов (XSS-поверхность: таблица, фильтр, очередь, дашборд)."""
    payload = 'КОФЕ" onmouseover="x=1 <img src=x onerror=alert(1)>'
    _add(client, "-300.00", payload)
    for url in ("/", "/dashboard", "/approve"):
        html = client.get(url).text
        # Сырая разметка из недоверенного описания не должна попадать в DOM: если автоэскейп
        # отключат, здесь появятся настоящий тег и настоящая кавычка (сейчас — &lt;img и &#34;).
        assert "<img src=x" not in html, url
        assert 'onmouseover="' not in html, url
    # data-* JSON дашборда остаётся сериализованным (tojson), а не «сырым» HTML
    dash = client.get("/dashboard").text
    match = re.search(r"data-cats='([^']*)'", dash)
    assert match and json.loads(match.group(1))  # парсится как JSON


def test_dashboard_chart_data_has_display_labels(client):
    """Донат-чарт получает RU-подписи (display_name), цвет — по слагу (cat_colors)."""
    _add(client, "-100.00", "ЛЕНТА")
    html = client.get("/dashboard").text
    match = re.search(r"data-cats='([^']*)'", html)
    assert match, "data-cats не найден"
    items = json.loads(match.group(1))  # Jinja tojson экранирует кириллицу в \uXXXX
    by_slug = {item["category"]: item.get("label") for item in items}
    assert by_slug.get("groceries") == "Продукты"


def test_import_hint_and_help_anchors_exist(client):
    index = client.get("/").text
    assert "повторный импорт не создаёт дублей" in index
    assert 'href="/help#faq-import-sber"' in index
    approve = client.get("/approve").text
    assert 'href="/help#faq-queue-why"' in approve
    help_html = client.get("/help").text
    for anchor in ("faq-import-sber", "faq-queue-why", "quick-start"):
        assert f'id="{anchor}"' in help_html, anchor


def test_filtered_empty_state(client):
    _add(client, "-50.00")
    html = client.get("/?category=household").text
    assert "Ничего не найдено по этому фильтру" in html
    assert "Сбросить фильтры" in html


def test_empty_month_state(client):
    _add(client, "-50.00", date="2026-09-12")
    html = client.get("/?month=2026-01").text
    assert "За Январь 2026 операций нет" in html


# ── M-5: дашборд — аномалии наверх, маркер темпа, дельты словами ─────────────

def test_dashboard_anomalies_card_first(client, tmp_path):
    """Аномалии недели — отдельная карточка ПЕРВЫМ блоком; в дайджесте их больше нет; дельты словами."""
    from datetime import UTC, datetime, timedelta

    today = datetime.now(UTC).date()
    s = Store(db_path=tmp_path / "ui.db")
    try:
        for i in range(10):  # медиана категории (90 дней)
            s.add_transaction(date=(today - timedelta(days=40 + i)).isoformat(),
                              description=f"ЛЕНТА {i}", amount_kopecks=-100_00,
                              category="groceries", category_source="import")
        s.add_transaction(date=(today - timedelta(days=2)).isoformat(), description="КРУПНАЯ ПОКУПКА",
                          amount_kopecks=-12000_00, category="groceries", category_source="import",
                          merchant="МЕГАМАРКЕТ")
        for desc in ("КОФЕ", "КОФЕ УГЛОВОЕ"):  # near-дубль в окне
            s.add_transaction(date=today.isoformat(), description=desc, amount_kopecks=-300_00,
                              category="restaurants", category_source="import", merchant="КОФЕ")
    finally:
        s.close()

    html = client.get("/dashboard").text
    assert 'id="anomalies-card"' in html
    assert html.index('id="anomalies-card"') < html.index('id="digest-card"')  # первый блок
    assert "крупная сумма" in html and "возможный дубль" in html
    assert 'href="/?month=' in html and "&q=" in html and ">Открыть</a>" in html
    assert 'aria-label="Открыть' in html  # O11 (Astra 02.10): пять одинаковых «Открыть» — с мерчантом
    assert "Аномалии (" not in html  # старая подсекция дайджеста убрана
    assert "к прошлому окну" in html and "Δ" not in html  # дельты словами, знак «Δ» убран


def test_dashboard_budget_tempo_marker_and_risk_order(client, tmp_path):
    """M-5: бюджеты — по риску (перерасход выше), маркер темпа = доля прошедшего месяца."""
    import calendar
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    month = today.strftime("%Y-%m")
    elapsed = round(today.day / calendar.monthrange(today.year, today.month)[1] * 100)
    s = Store(db_path=tmp_path / "ui.db")
    try:
        s.set_budget("fuel", 1000_00)        # 10% — спокойно
        s.set_budget("groceries", 1000_00)   # 120% — перерасход
        s.add_transaction(f"{month}-01", "ЛЕНТА", -1200_00, "groceries", "rule")
        s.add_transaction(f"{month}-02", "АЗС", -100_00, "fuel", "rule")
    finally:
        s.close()

    html = client.get(f"/dashboard?month={month}").text
    assert html.index("Продукты") < html.index("Топливо")  # перерасход выше (по риску, не по алфавиту)
    if 0 < elapsed < 100:  # маркер/легенда — только для текущего месяца (ревью 24.09)
        assert f"left: {elapsed}%" in html
        assert f"прошло {elapsed}% месяца" in html
    else:
        assert "отметка темпа" not in html


def test_index_forms_collapsed_and_totals_line(client):
    """M-6: данные выше форм — итоги строкой, «Импорт»/«Добавить» свёрнуты в кнопки шапки таблицы."""
    html = client.get("/").text
    # свёрнутые панели с формами (по умолчанию скрыты)
    assert '<div id="import-panel" hidden' in html
    assert '<div id="add-panel" hidden' in html
    # кнопки-переключатели с aria-состоянием (a11y)
    assert 'data-toggle="import-panel"' in html and 'aria-controls="import-panel"' in html
    assert 'aria-expanded="false"' in html
    assert 'data-toggle="add-panel"' in html and 'aria-controls="add-panel"' in html
    # импорт файлом + drop-zone
    assert 'id="import-drop"' in html and 'type="file"' in html and 'hx-encoding="multipart/form-data"' in html
    # итоги месяца — строкой, а не четырьмя KPI-карточками
    assert "Доход" in html and "Расход" in html and "Баланс" in html
    assert "grid-cols-2 sm:grid-cols-4" not in html


def test_nav_active_state(client):
    """Wave 1: активный пункт — пилюля bg-accent-soft/text-accent + aria-current; остальные приглушены."""
    import re as _re

    def pill_classes(html: str, href: str) -> str:
        m = _re.search(rf'<a href="{href}" class="nav-pill ([^"]*)"', html.split("</nav>")[0])
        assert m, f"пилюля {href} не найдена в nav"
        return m.group(1)

    home = client.get("/").text
    assert "bg-accent-soft" in pill_classes(home, "/")
    assert "text-accent" in pill_classes(home, "/")
    assert "text-fg-muted" in pill_classes(home, "/dashboard")

    dash = client.get("/dashboard").text
    assert "bg-accent-soft" in pill_classes(dash, "/dashboard")
    assert "text-fg-muted" in pill_classes(dash, "/")

    assert "bg-accent-soft" in pill_classes(client.get("/approve").text, "/approve")
    assert "bg-accent-soft" in pill_classes(client.get("/settings").text, "/settings")

    nav = dash.split("</nav>")[0]
    assert nav.count('aria-current="page"') == 1  # a11y: активный пункт (ревью 24.09)
    assert 'aria-current="page"' in nav.split('href="/dashboard"')[1].split(">")[0]


def test_no_semantic_alpha_chips_in_templates():
    """Ревью Opus 5 (C4): текстовые чипы — только `*-soft`; alpha-фоны семантических цветов запрещены.

    `bg-line/30`, `bg-canvas/40` и т.п. — нейтральная декор-подсветка, она допустима; запрещены
    полупрозрачные фоны ЦВЕТНЫХ ролей (именно они давали FAIL 3.56 на 12 px тексте).
    """
    from pathlib import Path

    templates = Path(__file__).resolve().parents[1] / "src" / "spendtrack" / "templates"
    bad = []
    for path in templates.rglob("*.html"):
        for m in re.finditer(r"\bbg-(?:warn|danger|accent|accent-2|info|income)(?:-bg)?/\d+", path.read_text(encoding="utf-8")):
            bad.append(f"{path.name}:{m.group(0)}")
    assert not bad, f"alpha-чипы семантических цветов в шаблонах: {bad}"


def test_card_headings_sentence_case(client):
    """P1-5: UPPERCASE — только заголовкам колонок; заголовки карточек — sentence case 15px."""
    index = client.get("/").text
    assert "uppercase tracking-wide" not in index.split("<thead>")[0]
    assert '<h2 class="text-[15px] font-semibold text-fg">Транзакции' in index

    dash = client.get("/dashboard").text  # без данных таблицы нет — uppercase негде взяться
    assert "uppercase tracking-wide" not in dash
    assert "Бюджеты месяца" in dash or "Данных пока нет" in dash


def test_garbage_date_does_not_brick_pages(client):
    """Аудит 24.09 (P0): нераспознанная дата не пишется в БД, а невалидный month не роняет страницы."""
    csv_text = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
                "Валюта операции;Категория;Описание\n"
                "1;05/09/2026;1234;Выполнено;-100,00;RUB;Продукты;МУСОР\n")
    r = client.post("/api/import", json={"bank": "sber", "csv": csv_text}).json()
    assert r["added"] == 0 and r["reasons"]["date_unrecognized"] == 1
    assert client.get("/").status_code == 200
    assert client.get("/dashboard").status_code == 200
    assert client.get("/?month=abc").status_code == 200
    assert client.get("/dashboard?month=x").status_code == 200
    assert client.get("/export.csv?month=x").status_code == 200
