"""Ф0 «Беларусь/BYN»: базовая валюта установки (settings) управляет агрегатами, форматами и импортом.

Правило: «валюты не смешиваются» сохраняется, но «базовая» — настройка (`SPENDTRACK_BASE_CURRENCY` /
settings.toml, default RUB), а не захардкоженный рубль. Тесты — на публичный интерфейс; `_row_tx` —
точечно (единица импорта, у адаптеров стабильные сигнатуры).
"""
from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from spendtrack.config import base_currency, load_settings
from spendtrack.csv_import import _row_tx
from spendtrack.digest import build_digest
from spendtrack.reports import budgets_progress, categories_with_totals, report_daily, report_month
from spendtrack.store import Store, currency_symbol, fingerprint, fmt_money


def _add(store: Store, day: str, kopecks: int, currency: str | None = None, desc: str = "ТЕСТ") -> int | None:
    return store.add_transaction(date=day, description=desc, amount_kopecks=kopecks,
                                 category="groceries", category_source="rule", currency=currency)


# ---- настройка и форматирование ----

def test_base_currency_setting_normalized_and_validated(tmp_path):
    (tmp_path / "settings.toml").write_text('base_currency = "byn"\n', encoding="utf-8")
    assert load_settings(config_dir=tmp_path).base_currency == "BYN"
    (tmp_path / "settings.toml").write_text('base_currency = "RUBL"\n', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(config_dir=tmp_path)


def test_base_currency_env(monkeypatch):
    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "byn")
    assert base_currency() == "BYN"


def test_fmt_money_symbols_and_base_default(monkeypatch):
    assert fmt_money(123456, "BYN") == "+1\u00a0234,56 Br"
    assert fmt_money(-123456, "RUB") == "\u22121\u00a0234,56 ₽"
    assert fmt_money(100, "USD") == "+1,00 USD"  # без символа в карте — код
    assert fmt_money(0, "BYN") == "0,00 Br"
    assert currency_symbol("BYN") == "Br"
    assert currency_symbol("RUB") == "₽"
    assert currency_symbol("CHF") == "CHF"

    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "BYN")
    assert fmt_money(100) == "+1,00 Br"  # дефолт — базовая валюта установки
    assert currency_symbol() == "Br"


# ---- агрегаты следуют базовой валюте ----

def test_reports_follow_base_currency(monkeypatch, store):
    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "BYN")
    store.add_transaction(date="2026-09-10", description="ТЕСТ", amount_kopecks=-10_000,
                          category="groceries", category_source="rule", currency="BYN")
    store.add_transaction(date="2026-09-11", description="ТЕСТ", amount_kopecks=-20_000,
                          category="groceries", category_source="rule", currency="RUB")
    store.add_transaction(date="2026-09-12", description="ТЕСТ", amount_kopecks=-30_000,
                          category="groceries", category_source="rule", currency="USD")
    store.add_transaction(date="2026-09-13", description="ТЕСТ", amount_kopecks=50_000,
                          category="income", category_source="rule", currency="BYN")

    rep = report_month(store, "2026-09")
    assert rep["income_k"] == 50_000
    assert rep["expense_k"] == -10_000
    assert rep["foreign_count"] == 2  # RUB + USD — вне итогов (и в сноске)

    assert [d["date"] for d in report_daily(store, "2026-09")] == ["2026-09-10", "2026-09-13"]
    totals = {r["category"]: r["total_k"] for r in categories_with_totals(store, "2026-09")}
    assert totals == {"groceries": -10_000, "income": 50_000}

    store.set_budget("groceries", 100_000)
    [bp] = budgets_progress(store, "2026-09")
    assert bp["spent_k"] == 10_000  # только BYN-расход


def test_digest_follows_base_currency(monkeypatch, store):
    from datetime import date

    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "BYN")
    _add(store, "2026-09-10", -10_000, "BYN")
    _add(store, "2026-09-11", -20_000, "RUB")
    d = build_digest(store, days=7, today=date(2026, 9, 15))
    assert d["expense_k"] == -10_000
    assert d["foreign_count"] == 1


def test_add_transaction_defaults_to_base(monkeypatch, store):
    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "BYN")
    tx_id = _add(store, "2026-09-20", -100)  # currency не передана
    row = store.conn.execute("SELECT currency FROM transactions WHERE id=?", (tx_id,)).fetchone()
    assert row["currency"] == "BYN"


# ---- fingerprint: код валюты только для НЕ-базовой ----

def test_fingerprint_currency_policy(monkeypatch):
    raw = "2026-09-01|-100|X|a|"
    plain = hashlib.sha1(raw.encode()).hexdigest()
    with_byn = hashlib.sha1((raw + "|BYN").encode()).hexdigest()
    with_rub = hashlib.sha1((raw + "|RUB").encode()).hexdigest()

    # база RUB (дефолт): RUB-отпечатки неизменны, BYN различается
    assert fingerprint("2026-09-01", -100, "X", "a", "", "RUB") == plain
    assert fingerprint("2026-09-01", -100, "X", "a", "", "BYN") == with_byn

    # база BYN: исключается уже BYN, а RUB входит в отпечаток
    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "BYN")
    assert fingerprint("2026-09-01", -100, "X", "a", "", "BYN") == plain
    assert fingerprint("2026-09-01", -100, "X", "a", "", "RUB") == with_rub


# ---- импорт: пустая валюта = базовая ----

def test_import_default_currency_is_base(monkeypatch):
    monkeypatch.setenv("SPENDTRACK_BASE_CURRENCY", "BYN")
    assert _row_tx("2026-09-01", "ЛЕНТА 077", "-10,00", "", "")["currency"] == "BYN"
    assert _row_tx("2026-09-01", "ЛЕНТА 077", "-10,00", "", "USD")["currency"] == "USD"
    assert _row_tx("2026-09-01", "ЛЕНТА 077", "-10,00", "", "руб")["currency"] == "RUB"
