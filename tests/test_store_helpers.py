from __future__ import annotations

from spendtrack.store import month_bounds, parse_amount


def test_month_bounds_rolls_year():
    assert month_bounds("2026-01") == ("2026-01-01", "2026-02-01")
    assert month_bounds("2026-09") == ("2026-09-01", "2026-10-01")
    assert month_bounds("2026-12") == ("2026-12-01", "2027-01-01")


def test_has_transactions_reflects_data(store):
    assert store.has_transactions() is False
    store.add_transaction("2026-09-01", "ЛЕНТА", parse_amount("-100"), "groceries", "manual")
    assert store.has_transactions() is True


def test_add_transaction_commit_false_defers(store):
    store.add_transaction("2026-09-01", "ЛЕНТА", parse_amount("-100"), "groceries", "manual",
                          commit=False)
    assert store.conn.in_transaction is True
    store.conn.commit()
    assert store.conn.in_transaction is False
    assert store.has_transactions() is True
