from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from spendtrack import cli
from spendtrack.recurring import detect_recurring, recurring_summary

TODAY = date(2026, 4, 10)


def _add(store, day: str, merchant: str, kopecks: int,
         category: str = "subscriptions", row: str = ""):
    return store.add_transaction(
        date=day, description=merchant, amount_kopecks=kopecks, category=category,
        category_source="import", merchant=merchant, export_rowid=row,
    )


def _monthly(store, merchant: str, kopecks: int, days: list[str],
             category: str = "subscriptions") -> None:
    for day in days:
        _add(store, day, merchant, kopecks, category)


def test_detects_monthly_subscription(store):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-04", "2026-03-06", "2026-04-05"])

    items = detect_recurring(store, today=TODAY)

    assert len(items) == 1
    s = items[0]
    assert s["merchant"] == "NETFLIX"
    assert s["category"] == "subscriptions"
    assert s["price_k"] == 19900
    assert s["occurrences"] == 4
    assert s["first_date"] == "2026-01-05"
    assert s["last_date"] == "2026-04-05"
    assert s["median_gap_days"] == 30
    assert s["skipped_months"] == 0
    assert s["days_since_last"] == 5
    assert s["active"] is True
    assert s["next_expected"] == "2026-05-05"


def test_amount_drift_within_tolerance_keeps_subscription(store):
    """+5.03% (20900/19900): сходится — сравнение с бегущей медианой кластера (допуск растёт)."""
    _monthly(store, "YANDEX PLUS", -19900, ["2026-01-05", "2026-02-04", "2026-03-06"])
    _add(store, "2026-04-05", "YANDEX PLUS", -20900)

    items = detect_recurring(store, today=TODAY)

    assert len(items) == 1
    assert items[0]["price_k"] == 19900  # медиана кластера, а не последний платёж
    assert items[0]["occurrences"] == 4


def test_price_jump_splits_into_two_subscriptions(store):
    """Разрыв >5% — другой кластер: у мерчанта две подписки разных цен."""
    _monthly(store, "ЯНДЕКС", -19900, ["2026-01-05", "2026-02-04", "2026-03-06"])
    _monthly(store, "ЯНДЕКС", -29900, ["2026-01-20", "2026-02-19", "2026-03-21"])

    items = detect_recurring(store, today=TODAY)

    assert [s["price_k"] for s in items] == [29900, 19900]


def test_two_occurrences_is_not_recurring(store):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-04"])

    assert detect_recurring(store, today=TODAY) == []


def test_irregular_gap_is_not_recurring(store):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-04", "2026-02-14"])

    assert detect_recurring(store, today=TODAY) == []


def test_gap_boundaries_accepted(store):
    """27 и 34 дня по краям допуска (медиана 30.5→30)."""
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-01", "2026-03-07"])

    items = detect_recurring(store, today=date(2026, 3, 10))

    assert len(items) == 1
    assert items[0]["median_gap_days"] == 30


def test_gap_outside_bounds_rejected(store):
    """26 и 35 дней — уже не месячный цикл."""
    _monthly(store, "NETFLIX", -19900, ["2026-01-01", "2026-01-27"])
    _add(store, "2026-03-03", "NETFLIX", -19900)  # 27.01 → 03.03 = 35 дней

    assert detect_recurring(store, today=TODAY) == []


def test_one_skipped_month_allowed(store):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-04", "2026-04-05"])

    items = detect_recurring(store, today=TODAY)

    assert len(items) == 1
    assert items[0]["skipped_months"] == 1
    assert items[0]["occurrences"] == 3


def test_two_skipped_months_rejected(store):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-03-06", "2026-05-05"])

    assert detect_recurring(store, today=TODAY) == []


def test_transfers_and_income_ignored(store):
    _monthly(store, "ДРУГ", -19900, ["2026-01-05", "2026-02-04", "2026-03-06"], category="transfers")
    _monthly(store, "ЗАРПЛАТА", 2500000, ["2026-01-05", "2026-02-04", "2026-03-06"], category="income")

    assert detect_recurring(store, today=TODAY) == []


def test_empty_merchant_ignored(store):
    for day in ["2026-01-05", "2026-02-04", "2026-03-06"]:
        store.add_transaction(date=day, description="БЕЗ МЕРЧАНТА", amount_kopecks=-19900,
                              category="subscriptions", category_source="import", merchant=None)

    assert detect_recurring(store, today=TODAY) == []


def test_stale_subscription_marked_not_active(store):
    _monthly(store, "NETFLIX", -19900, ["2025-11-05", "2025-12-05", "2026-01-05"])

    items = detect_recurring(store, today=date(2026, 3, 1))

    assert len(items) == 1
    assert items[0]["active"] is False
    assert items[0]["days_since_last"] == 55


def test_same_day_charges_count_once(store):
    """Дубль-списание в один день — не «повтор месяца» (считаем уникальные даты)."""
    _add(store, "2026-01-05", "NETFLIX", -19900)
    _add(store, "2026-01-05", "NETFLIX", -19900, row="r2")
    _monthly(store, "NETFLIX", -19900, ["2026-02-04", "2026-03-06"])

    items = detect_recurring(store, today=TODAY)

    assert len(items) == 1
    assert items[0]["occurrences"] == 3


def test_price_median_counts_all_charges_even_same_day(store):
    """Цена — медиана по всем списаниям кластера (дни уникальны только для интервалов)."""
    _add(store, "2026-01-05", "NETFLIX", -20900)
    _add(store, "2026-02-04", "NETFLIX", -20900)
    _add(store, "2026-03-06", "NETFLIX", -19900)
    _add(store, "2026-03-06", "NETFLIX", -19900, row="r2")
    _add(store, "2026-03-06", "NETFLIX", -19900, row="r3")

    items = detect_recurring(store, today=TODAY)

    assert len(items) == 1
    assert items[0]["price_k"] == 19900  # медиана по всем 5 списаниям
    assert items[0]["occurrences"] == 3  # но повторов — 3 уникальных дня


def test_category_is_most_frequent(store):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-04", "2026-03-06"])
    _add(store, "2026-04-05", "NETFLIX", -19900, category="entertainment")

    items = detect_recurring(store, today=TODAY)

    assert items[0]["category"] == "subscriptions"


def test_summary_sorts_active_first_and_totals_monthly(store):
    _monthly(store, "NETFLIX", -19900, ["2026-02-04", "2026-03-06", "2026-04-05"])
    _monthly(store, "СТАРАЯ ПОДПИСКА", -9900, ["2025-10-05", "2025-11-04", "2025-12-06"])

    summary = recurring_summary(store, today=TODAY)

    assert [s["merchant"] for s in summary["subscriptions"]] == ["NETFLIX", "СТАРАЯ ПОДПИСКА"]
    assert summary["active_count"] == 1
    assert summary["stale_count"] == 1
    assert summary["monthly_total_k"] == 19900  # stale в итог не входит


def test_cli_recurring_table_and_json(monkeypatch, capsys, store):
    """CLI: таблица + --json; даты относительно сегодня — тест не зависит от календаря."""
    base = datetime.now(UTC).date()
    days = [(base - timedelta(days=n)).isoformat() for n in (65, 35, 5)]
    _monthly(store, "NETFLIX", -19900, days)
    monkeypatch.setattr(cli, "make_store", lambda: store)

    assert cli.main(["recurring"]) == 0
    out = capsys.readouterr().out
    assert "NETFLIX" in out
    assert "-199.00 / мес" in out
    assert "найдено 1" in out and "активных 1" in out

    assert cli.main(["recurring", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_count"] == 1
    assert payload["monthly_total_k"] == 19900
    assert payload["subscriptions"][0]["merchant"] == "NETFLIX"


def test_cli_recurring_empty(monkeypatch, capsys, store):
    monkeypatch.setattr(cli, "make_store", lambda: store)

    assert cli.main(["recurring"]) == 0
    assert "найдено 0" in capsys.readouterr().out


def test_recurring_summary_reuses_precomputed_subscriptions(store, monkeypatch):
    _monthly(store, "NETFLIX", -19900, ["2026-01-05", "2026-02-04", "2026-03-06", "2026-04-05"])
    expected = recurring_summary(store, today=TODAY)
    subs = detect_recurring(store, today=TODAY)

    def _boom(*args, **kwargs):
        raise AssertionError("detect_recurring должен переиспользоваться")

    monkeypatch.setattr("spendtrack.recurring.detect_recurring", _boom)
    assert recurring_summary(store, today=TODAY, subscriptions=subs) == expected

