"""Wave 1 «Стикербук» — лэйаут: KPI-бенто, nav-пилюли, постеры пустых состояний, count-up процентов.

Usage-first: проверяем то, что видно на публичных страницах (HTML), а не внутренности шаблонов.
Дизайн и числа — DESIGN_DIRECTION_V2_2026-09-29.md §4.1–4.4; контрасты — test_tokens_contrast.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.store import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "wave1.db"))
    return TestClient(app)


def _add(client: TestClient, amount: str, desc: str = "ЛЕНТА", date: str = "2026-09-12") -> None:
    r = client.post("/api/transactions", json={"date": date, "description": desc, "amount": amount})
    assert r.status_code == 200


# ── KPI-бенто (§4.2) ────────────────────────────────────────────────────────

def test_dashboard_kpi_bento_primary_two_columns_and_sums(client):
    """Дашборд: primary-плитка (баланс) — 2 колонки, суммы 24–30 px, tint-плитки дохода/расхода."""
    _add(client, "50000.00", "ЗАРПЛАТА")
    _add(client, "-1234.56", "ЛЕНТА")
    html = client.get("/dashboard?month=2026-09").text

    assert 'id="kpi-balance"' in html
    assert "col-span-2" in html
    assert "bg-income-soft" in html and "bg-accent-soft" in html  # «цвет = смысл»: tint по роли
    assert "text-3xl" in html and "text-2xl" in html              # числа — герои (§3.7)
    assert "tabular-nums" in html
    # переключатель месяца абсолютный и живёт над бенто
    assert 'id="dash-month"' in html
    assert 'href="/dashboard?month=2026-08"' in html
    assert 'href="/dashboard?month=2026-10"' in html


def test_dashboard_budget_percent_is_countup_but_money_is_not(client, tmp_path):
    """Count-up — только целые проценты бюджета (деньги не анимируются: формат сервера)."""
    store = Store(db_path=tmp_path / "wave1.db")
    try:
        store.set_budget("groceries", 100_000)  # 1 000 ₽
    finally:
        store.close()
    _add(client, "-250.00", "ЛЕНТА")  # 25% бюджета

    html = client.get("/dashboard?month=2026-09").text
    assert 'data-countup="25"' in html
    assert 'data-countup-suffix="%"' in html
    assert html.count("data-countup=") == 1  # деньги в разметке — без анимации


# ── Постеры пустых состояний (§4.4) ─────────────────────────────────────────

def test_empty_list_poster(client):
    """Первый запуск на главной: постер (один бренд-момент) + действие + справка."""
    html = client.get("/").text
    assert "Пока нет транзакций" in html
    assert 'class="poster' in html
    assert 'href="/help#faq-import-sber"' in html


def test_empty_queue_poster(client):
    """Пустая очередь: постер «Все подтверждены» вместо голой строки таблицы."""
    html = client.get("/approve").text
    assert "Все подтверждены" in html
    assert 'class="poster' in html
    assert 'href="/help#faq-queue-why"' in html


def test_dashboard_onboarding_poster(client):
    """Дашборд без данных: онбординг — постер; действия (импорт/очередь/справка) на месте."""
    html = client.get("/dashboard").text
    assert 'id="onboarding"' in html
    assert 'class="poster' in html
    for href in ('href="/#import"', 'href="/#add"', 'href="/approve"', 'href="/help#quick-start"'):
        assert href in html, href


def test_dashboard_empty_month_poster_single(client):
    """Пустой месяц при данных: постер есть, онбординга нет (один постер на экран)."""
    _add(client, "-50.00")
    html = client.get("/dashboard?month=2026-01").text
    assert "За Январь 2026 операций нет" in html
    assert 'class="poster' in html
    assert 'id="onboarding"' not in html


def test_expense_rows_decor(client):
    """Wave 1.3 «Расходы»: аватар категории (иконка-стикер), таймлайн-день, класс каскада строк."""
    _add(client, "-123.45", "ЛЕНТА")
    html = client.get("/?month=2026-09").text
    assert 'class="tx-avatar' in html and "#i-groceries" in html
    assert "color-mix(in srgb, #22c55e 16%" in html  # софт-тинт аватара в цвете категории
    assert 'class="tx-day' in html
    assert 'class="tx-row' in html


# ── Микро-моушен (§4.4) ─────────────────────────────────────────────────────

def test_pending_chip_has_chip_pop(client):
    """Счётчик очереди — носитель «попа» после htmx-свапа: и в шапке, и в OOB-фрагменте."""
    html = client.get("/").text
    assert 'id="pending-count"' in html and "chip-pop" in html
    oob = client.get("/api/reviews/count").text
    assert 'id="pending-count"' in oob and "chip-pop" in oob
