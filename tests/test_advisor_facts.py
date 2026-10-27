from __future__ import annotations

import json
from datetime import date

import pytest

from spendtrack.advisor.facts import build_facts, parse_period, validate_facts
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy


@pytest.fixture()
def store(tmp_path):
    s = Store(db_path=tmp_path / "facts.db")
    yield s
    s.close()


def add(store, day, amount, category, desc="x", merchant=None, currency=None):
    return store.add_transaction(day, desc, amount, category, "rule",
                                 merchant=merchant, currency=currency)


def test_parse_period_this_month():
    p = parse_period("сколько в этом месяце?", today=date(2026, 10, 27))
    assert p is not None
    assert (p.month, p.start, p.end) == ("2026-10", "2026-10-01", "2026-10-31")


def test_parse_period_previous_month_rollover():
    p = parse_period("прошлый месяц", today=date(2027, 1, 5))
    assert p is not None and p.month == "2026-12"


def test_parse_period_last_days():
    p = parse_period("последние 30 дней", today=date(2026, 10, 27))
    assert p is not None
    assert p.month is None and p.start == "2026-09-28" and p.end == "2026-10-27"


def test_parse_period_explicit_month_and_bounds():
    p = parse_period("2026-05", today=date(2026, 10, 27))
    assert p is not None and p.month == "2026-05"
    assert parse_period("последние 0 дней", today=date(2026, 10, 27)) is None
    assert parse_period("последние 400 дней", today=date(2026, 10, 27)) is None


def test_parse_period_bare_month_is_most_recent_not_future():
    p = parse_period("за декабрь", today=date(2026, 10, 27))
    assert p is not None and p.month == "2025-12"
    p2 = parse_period("в мае", today=date(2026, 10, 27))
    assert p2 is not None and p2.month == "2026-05"


def test_build_facts_month(store):
    add(store, "2026-10-05", -100_000, "groceries",
        desc="SENTINEL_MERCHANT_7f3a", merchant="SENTINEL_MERCHANT_7f3a",
        currency="RUB")
    add(store, "2026-10-06", -50_000, "restaurants")
    add(store, "2026-10-07", 200_000, "income")
    add(store, "2026-10-08", -10_000, "groceries", desc="usd", currency="USD")
    store.set_budget("groceries", 80_000)

    facts = build_facts(store, parse_period("2026-10", today=date(2026, 10, 27)),
                        taxonomy=load_taxonomy())
    validate_facts(facts, taxonomy=load_taxonomy())

    assert facts["total"] == 150_000
    assert facts["tx_count"] == 3
    cats = {c["name"]: c for c in facts["categories"]}
    assert set(cats) == {"groceries", "restaurants"}
    assert cats["groceries"]["sum"] == 100_000 and cats["groceries"]["count"] == 1
    assert cats["restaurants"]["sum"] == 50_000
    share = {c["name"]: c["share_bp"] for c in facts["categories"]}
    assert share == {"groceries": 6667, "restaurants": 3333}
    assert facts["budgets"] == [{"category": "groceries", "limit": 80_000,
                                 "spent": 100_000, "overrun": 20_000}]
    assert facts["excluded_foreign"] == {"count": 1, "currencies": ["USD"]}
    assert facts["unavailable"] == []
    # daily is spend-only (income day omitted)
    assert {d["date"]: d["sum"] for d in facts["daily"]} == {
        "2026-10-05": 100_000, "2026-10-06": 50_000}
    assert "SENTINEL_MERCHANT_7f3a" not in json.dumps(facts, ensure_ascii=False)


def test_build_facts_empty_month(store):
    facts = build_facts(store, parse_period("2026-01", today=date(2026, 10, 27)),
                        taxonomy=load_taxonomy())
    validate_facts(facts, taxonomy=load_taxonomy())
    assert facts["total"] == 0 and facts["tx_count"] == 0
    assert facts["categories"] == [] and facts["budgets"] == [] and facts["daily"] == []
    assert facts["compare"]["total"] == 0


def test_build_facts_foreign_only(store):
    add(store, "2026-10-05", -10_000, "groceries", currency="USD", desc="usd")
    facts = build_facts(store, parse_period("2026-10", today=date(2026, 10, 27)),
                        taxonomy=load_taxonomy())
    validate_facts(facts, taxonomy=load_taxonomy())
    assert facts["total"] == 0 and facts["tx_count"] == 0
    assert facts["excluded_foreign"] == {"count": 1, "currencies": ["USD"]}


def test_build_facts_last_days_slices_daily(store):
    add(store, "2026-09-27", -1_000, "groceries")   # outside 30d window
    add(store, "2026-09-29", -2_000, "groceries")
    add(store, "2026-10-02", -3_000, "restaurants")
    add(store, "2026-10-27", -4_000, "transport")
    facts = build_facts(store, parse_period("последние 30 дней", today=date(2026, 10, 27)),
                        taxonomy=load_taxonomy())
    validate_facts(facts, taxonomy=load_taxonomy())
    assert facts["total"] == 9_000 and facts["tx_count"] == 3
    assert facts["categories"] is None and facts["budgets"] is None
    assert facts["unavailable"] == ["categories", "budgets"]
    assert [d["date"] for d in facts["daily"]] == ["2026-09-29", "2026-10-02", "2026-10-27"]


def test_validate_facts_rejects_extra_keys_and_non_taxonomy(store):
    add(store, "2026-10-05", -1_000, "groceries")
    facts = build_facts(store, parse_period("2026-10", today=date(2026, 10, 27)),
                        taxonomy=load_taxonomy())
    bad = dict(facts)
    bad["merchant"] = "x"
    with pytest.raises(ValueError):
        validate_facts(bad, taxonomy=load_taxonomy())
    bad2 = json.loads(json.dumps(facts))
    bad2["categories"][0]["name"] = "Пятёрочка"
    with pytest.raises(ValueError):
        validate_facts(bad2, taxonomy=load_taxonomy())
    bad3 = dict(facts)
    bad3["total"] = "1000"
    with pytest.raises(ValueError):
        validate_facts(bad3, taxonomy=load_taxonomy())


def test_partial_month_compare_uses_same_day_range(store):
    add(store, "2026-10-05", -100_00, "groceries")
    add(store, "2026-09-03", -40_00, "groceries")
    add(store, "2026-09-20", -60_00, "groceries")
    today = date(2026, 10, 10)
    facts = build_facts(store, parse_period("2026-10", today=today),
                        taxonomy=load_taxonomy(), today=today)
    assert facts["total"] == 100_00
    assert facts["compare"]["total"] == 40_00          # Sep 1..10 only
    assert facts["compare"]["label"] == "2026-09 по 10"
