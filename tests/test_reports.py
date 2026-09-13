from __future__ import annotations

from spendtrack.reports import categories_with_totals, report_daily, report_month
from spendtrack.store import parse_amount


def _populate(store):
    store.add_transaction("2026-09-01", "ЛЕНТА", parse_amount("-1234.50"), "groceries", "rule", merchant="ЛЕНТА")
    store.add_transaction("2026-09-02", "UBER", parse_amount("-1200"), "transport", "rule", merchant="UBER")
    store.add_transaction("2026-09-03", "Зарплата", parse_amount("250000"), "income", "rule", merchant="ZP")
    store.add_transaction("2026-09-04", "NETFLIX", parse_amount("-1549"), "subscriptions", "rule", merchant="NETFLIX")
    store.add_transaction("2026-10-01", "ОЗОН", parse_amount("-500"), "household", "rule")


def test_report_month_summary(store):
    _populate(store)
    rep = report_month(store, "2026-09")
    assert rep["income_k"] == 250000 * 100       # 250000 руб = 25 000 000 коп
    assert rep["expense_k"] == -123450 - 120000 - 154900  # -398350 коп


def test_report_month_excludes_other_months(store):
    _populate(store)
    rep = report_month(store, "2026-09")
    cats = {c["category"]: c for c in rep["categories"]}
    assert "household" not in cats


def test_categories_layout(store):
    _populate(store)
    totals = categories_with_totals(store, "2026-09")
    names = [c["category"] for c in totals]
    assert names == sorted(names)


def test_empty_db(store):
    rep = report_month(store, "2026-09")
    assert rep["income_k"] == 0
    assert rep["expense_k"] == 0
    assert rep["categories"] == []


def test_report_daily_series(store):
    _populate(store)
    series = report_daily(store, "2026-09")
    by_date = {d["date"]: d for d in series}
    assert by_date["2026-09-01"]["total_k"] == -123450
    assert "2026-10-01" not in by_date
    assert all(d["date"] >= "2026-09-01" and d["date"] <= "2026-09-30" for d in series)


def test_report_daily_empty(store):
    assert report_daily(store, "2026-09") == []