from __future__ import annotations

from datetime import date

import pytest

from spendtrack.advisor.slots import Slots, category_aliases, parse_slot_payload, parse_slots
from spendtrack.taxonomy import Category, Taxonomy, load_taxonomy

TODAY = date(2026, 10, 27)


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def test_total_this_month(taxonomy):
    s = parse_slots("сколько потратил в этом месяце?", TODAY, taxonomy)
    assert s.metric == "total" and s.period.month == "2026-10"
    assert s.category is None and s.ask_back is None


def test_category_previous_month(taxonomy):
    s = parse_slots("сколько на продукты в прошлом месяце?", TODAY, taxonomy)
    assert s.metric == "category" and s.category == "groceries"
    assert s.period.month == "2026-09"


def test_budget_overrun(taxonomy):
    s = parse_slots("где перерасход по бюджетам?", TODAY, taxonomy)
    assert s.metric == "budget"


def test_trend_last_days(taxonomy):
    s = parse_slots("тренд за последние 30 дней", TODAY, taxonomy)
    assert s.metric == "trend" and s.period.month is None
    assert s.period.start == "2026-09-28" and s.compare is True


def test_top_n_parsed(taxonomy):
    s = parse_slots("топ-5 категорий за октябрь", TODAY, taxonomy)
    assert s.metric == "top" and s.top_n == 5 and s.period.month == "2026-10"


def test_top_n_invalid_asks_back(taxonomy):
    s = parse_slots("топ-20 категорий", TODAY, taxonomy)
    assert s.metric == "unknown" and s.ask_back == "top_n"


def test_bad_period_asks_back(taxonomy):
    s = parse_slots("сколько за последние 400 дней", TODAY, taxonomy)
    assert s.metric == "unknown" and s.ask_back == "period"


@pytest.mark.parametrize("text,month", [
    ("в январе", "2026-01"), ("в феврале", "2026-02"), ("в марте", "2026-03"),
    ("в апреле", "2026-04"), ("в мае", "2026-05"), ("в июне", "2026-06"),
    ("в июле", "2026-07"), ("в августе", "2026-08"), ("в сентябре", "2026-09"),
    ("в октябре", "2026-10"), ("в ноябре", "2025-11"), ("в декабре", "2025-12"),
])
def test_all_month_forms(taxonomy, text, month):
    s = parse_slots(f"сколько {text}", TODAY, taxonomy)
    assert s.period.month == month


def test_alias_map_is_unique(taxonomy):
    aliases = category_aliases(taxonomy)
    collisions = {a: names for a, names in aliases.items() if len(names) > 1}
    assert collisions == {}, collisions


def test_ambiguous_alias_asks_back():
    tx = Taxonomy([
        Category("groceries", "#111111", "продукты"),
        Category("restaurants", "#222222", "продукты"),
    ], [])
    s = parse_slots("сколько на продукты", TODAY, tx)
    assert s.metric == "unknown" and s.ask_back == "ambiguous_category"


def test_garbage_payload_rejected(taxonomy):
    assert parse_slot_payload({"metric": "forecast"}, taxonomy) is None
    assert parse_slot_payload({"metric": "category", "category": "Пятёрочка"},
                              taxonomy) is None
    assert parse_slot_payload({"metric": "top", "top_n": 99}, taxonomy) is None
    ok = parse_slot_payload({"metric": "category", "category": "groceries"}, taxonomy)
    assert ok is not None and ok["category"] == "groceries"


def test_slots_carry_no_raw_text(taxonomy):
    s = parse_slots("сколько на продукты SENTINEL_MERCHANT_7f3a", TODAY, taxonomy)
    assert set(Slots.__dataclass_fields__) == {
        "period", "metric", "category", "top_n", "compare", "ask_back"}
    assert "SENTINEL_MERCHANT_7f3a" not in repr(s)
