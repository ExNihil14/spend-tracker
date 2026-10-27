from __future__ import annotations

from datetime import date

import pytest

from spendtrack.advisor.answer import Answer, answer, plural_ru
from spendtrack.advisor.facts import Period
from spendtrack.advisor.slots import Slots
from spendtrack.taxonomy import load_taxonomy

TODAY = date(2026, 10, 10)


def facts(**kw):
    base = {
        "period": {"start": "2026-10-01", "end": "2026-10-31", "label": "2026-10",
                   "month": "2026-10"},
        "base_currency": "RUB",
        "total": 150_000,
        "tx_count": 3,
        "categories": [{"name": "groceries", "sum": 100_000, "count": 1,
                        "share_bp": 6667},
                       {"name": "restaurants", "sum": 50_000, "count": 2,
                        "share_bp": 3333}],
        "budgets": [],
        "daily": [{"date": "2026-10-05", "sum": 100_000},
                  {"date": "2026-10-06", "sum": 50_000}],
        "excluded_foreign": {"count": 0, "currencies": []},
        "compare": {"total": 100_000, "daily": [], "label": "2026-09"},
        "unavailable": [],
    }
    base.update(kw)
    return base


def slots(**kw):
    s = {"period": Period("2026-10-01", "2026-10-31", "2026-10", "2026-10"),
         "metric": "total", "category": None, "top_n": 3, "compare": False,
         "ask_back": None}
    s.update(kw)
    return Slots(**s)


@pytest.mark.parametrize("n,word", [
    (1, "операция"), (2, "операции"), (5, "операций"), (11, "операций"),
    (21, "операция"), (22, "операции"), (25, "операций"),
])
def test_plural_ru(n, word):
    assert plural_ru(n, "операция", "операции", "операций") == word


def test_total_with_compare():
    a = answer(facts(), slots(compare=True), load_taxonomy(), TODAY)
    assert isinstance(a, Answer)
    assert a.text == ("За 2026-10 — 1500.00 ₽ (3 операции). "
                      "К прошлому периоду: +50.0%.")


def test_total_compare_no_previous_data():
    a = answer(facts(compare={"total": 0, "daily": [], "label": "2026-09"}),
               slots(compare=True), load_taxonomy(), TODAY)
    assert "нет данных" in a.text


def test_category_share_and_missing():
    tx = load_taxonomy()
    a = answer(facts(), slots(metric="category", category="groceries"), tx, TODAY)
    assert a.text.startswith(f"{tx.display('groceries')}: 1000.00 ₽ (66.7%, 1 операция)")
    b = answer(facts(), slots(metric="category", category="health"), tx, TODAY)
    assert b.text.endswith("0.00 ₽ (0 операций).")


def test_budget_overrun_and_ok():
    tx = load_taxonomy()
    over = facts(budgets=[{"category": "groceries", "limit": 80_000,
                           "spent": 100_000, "overrun": 20_000}])
    a = answer(over, slots(metric="budget"), tx, TODAY)
    assert "Перерасход" in a.text and "+200.00 ₽" in a.text and "125%" in a.text
    ok = answer(facts(budgets=[]), slots(metric="budget"), tx, TODAY)
    assert ok.text == "В рамках бюджетов."


def test_trend_average_and_peak():
    a = answer(facts(), slots(metric="trend"), load_taxonomy(), TODAY)
    # current month, today 10th -> divisor 10
    assert a.text == ("Средний день 150.00 ₽; максимум 2026-10-05 — 1000.00 ₽.")


def test_top_n_limits_list():
    cats = [{"name": "groceries", "sum": 90_000, "count": 1, "share_bp": 6000},
            {"name": "restaurants", "sum": 30_000, "count": 1, "share_bp": 2000},
            {"name": "transport", "sum": 20_000, "count": 1, "share_bp": 1333},
            {"name": "fuel", "sum": 10_000, "count": 1, "share_bp": 667}]
    a = answer(facts(categories=cats), slots(metric="top", top_n=2), load_taxonomy(), TODAY)
    assert a.text.startswith("Топ-2: ") and a.text.count("—") == 2


@pytest.mark.parametrize("reason", ["period", "top_n", "ambiguous_category", "unknown"])
def test_ask_back_reasons(reason):
    a = answer(facts(), slots(metric="unknown", ask_back=reason), load_taxonomy(), TODAY)
    assert a.intent == "ask_back" and a.text


def test_no_raw_text_in_answer():
    a = answer(facts(), slots(compare=True), load_taxonomy(), TODAY)
    assert "SENTINEL" not in a.text
