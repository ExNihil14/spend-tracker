from __future__ import annotations

from spendtrack.categorize import categorize_rules_only
from spendtrack.store import parse_amount


def test_rule_lenta(taxonomy, store):
    tx = {"description": "Покупка в ЛЕНТА", "amount_kopecks": parse_amount("-500")}
    assert categorize_rules_only(tx, taxonomy, store) == "groceries"


def test_rule_tatneft(taxonomy, store):
    tx = {"description": "АЗС ТАТНЕФТЬ 042", "amount_kopecks": parse_amount("-2000")}
    assert categorize_rules_only(tx, taxonomy, store) == "fuel"


def test_rule_zarabotnaya_not_zarplata(taxonomy, store):
    """Урок с гейта №3: правило 'ЗАРПЛАТА' не ловит 'ЗАРАБОТНАЯ ПЛАТА'."""
    tx = {"description": "ЗАРАБОТНАЯ ПЛАТА ООО", "amount_kopecks": parse_amount("250000")}
    assert categorize_rules_only(tx, taxonomy, store) == "income"


def test_rule_unknown_falls_through(taxonomy, store):
    tx = {"description": "БУРГЕР КИНГ", "amount_kopecks": parse_amount("-300")}
    assert categorize_rules_only(tx, taxonomy, store) is None


def test_rule_netflix(taxonomy, store):
    tx = {"description": "NETFLIX.COM", "amount_kopecks": parse_amount("-1549")}
    assert categorize_rules_only(tx, taxonomy, store) == "subscriptions"