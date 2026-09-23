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


def test_update_merchant_and_needs_review_filter(store):
    """Аудит 23.09 (P0): update_merchant и list_transactions(needs_review=True)."""
    store.add_transaction("2026-09-01", "АЗС", parse_amount("-100"), "other", "manual")
    tx_id = store.conn.execute("SELECT id FROM transactions").fetchone()["id"]
    store.update_merchant(tx_id, "ЛУКОЙЛ")
    assert store.get_transaction(tx_id)["merchant"] == "ЛУКОЙЛ"

    store.add_transaction("2026-09-02", "КАФЕ", parse_amount("-300"), "other",
                          "llm_pending_review", review_status="pending")
    store.add_transaction("2026-09-03", "ЛЕНТА", parse_amount("-200"), "groceries",
                          "rule", review_status="approved")

    pending = store.list_transactions(needs_review=True)
    assert [t["description"] for t in pending] == ["КАФЕ"]


def test_add_transaction_commit_false_defers(store):
    store.add_transaction("2026-09-01", "ЛЕНТА", parse_amount("-100"), "groceries", "manual",
                          commit=False)
    assert store.conn.in_transaction is True
    store.conn.commit()
    assert store.conn.in_transaction is False
    assert store.has_transactions() is True
