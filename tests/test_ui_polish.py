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
    assert 'href="/?month=2026-09&category=groceries"' in html
    assert 'hx-boost="false"' in html
    assert ">Продукты</option>" in html  # фильтр-селект — RU-имена, не слаги


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
    assert 'href="/?q=' in html and ">Открыть</a>" in html
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
    assert f"left: {elapsed}%" in html
    assert f"прошло {elapsed}% месяца" in html


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
