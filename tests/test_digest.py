from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from spendtrack import cli
from spendtrack.digest import build_digest

TODAY = date(2026, 6, 15)


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _add(store, day: str, kopecks: int, category: str = "groceries",
         merchant: str = "МАГАЗИН", desc: str | None = None, row: str = ""):
    return store.add_transaction(
        date=day, description=desc or merchant, amount_kopecks=kopecks,
        category=category, category_source="import", merchant=merchant, export_rowid=row,
    )


# ── Итоги окна ──────────────────────────────────────────────────────────────

def test_empty_digest(store):
    d = build_digest(store, days=7, today=TODAY)

    assert d["period"] == {"from": "2026-06-09", "to": "2026-06-15", "days": 7}
    assert d["prev_period"] == {"from": "2026-06-02", "to": "2026-06-08"}
    assert d["income_k"] == 0 and d["expense_k"] == 0 and d["balance_k"] == 0
    assert d["expense_delta_k"] == 0
    assert d["avg_per_day_k"] == 0
    assert d["top_categories"] == [] and d["top_day"] is None
    assert d["pending_count"] == 0
    assert d["upcoming"] == [] and d["anomalies"] == []


def test_totals_windows_and_delta(store):
    _add(store, _day(0), -10000)            # текущее окно (граница)
    _add(store, _day(-6), -5000)            # текущее окно (первый день)
    _add(store, _day(-1), 50000, "income")  # доход в окне
    _add(store, _day(-7), -20000)           # прошлое окно (последний день)
    _add(store, _day(-15), -70000)          # вне обоих окон (прошлое: 02.06..08.06)

    d = build_digest(store, days=7, today=TODAY)

    assert d["expense_k"] == -15000
    assert d["income_k"] == 50000
    assert d["balance_k"] == 35000
    assert d["prev"]["expense_k"] == -20000
    assert d["expense_delta_k"] == 5000  # траты снизились на 50 ₽
    assert d["transaction_count"] == 3


def test_transfers_excluded_everywhere(store):
    _add(store, _day(-1), -100000, "transfers")

    d = build_digest(store, days=7, today=TODAY)

    assert d["expense_k"] == 0 and d["balance_k"] == 0
    assert d["top_categories"] == [] and d["top_day"] is None
    assert d["avg_per_day_k"] == 0 and d["anomalies"] == []


def test_income_only_in_totals(store):
    _add(store, _day(-1), 50000, "income")

    d = build_digest(store, days=7, today=TODAY)

    assert d["income_k"] == 50000
    assert d["top_categories"] == [] and d["top_day"] is None


def test_top_categories_deltas_and_sort(store):
    _add(store, _day(-1), -30000, "restaurants")
    _add(store, _day(-2), -20000, "groceries")
    _add(store, _day(-9), -5000, "groceries")  # прошлое окно (today-14..-8)

    d = build_digest(store, days=7, today=TODAY)

    assert [c["category"] for c in d["top_categories"]] == ["restaurants", "groceries"]
    top = d["top_categories"][0]
    assert top["total_k"] == -30000 and top["prev_k"] == 0 and top["delta_k"] == -30000
    assert top["count"] == 1
    assert d["top_categories"][1]["delta_k"] == -15000


def test_top_day_and_avg_per_day(store):
    _add(store, _day(-1), -30000)
    _add(store, _day(-2), -10000)

    d = build_digest(store, days=7, today=TODAY)

    assert d["top_day"] == {"date": _day(-1), "total_k": -30000}
    assert d["avg_per_day_k"] == -5714  # round(-40000 / 7)


def test_single_day_window(store):
    _add(store, _day(0), -5000)
    _add(store, _day(-1), -4000)

    d = build_digest(store, days=1, today=TODAY)

    assert d["period"] == {"from": _day(0), "to": _day(0), "days": 1}
    assert d["prev_period"] == {"from": _day(-1), "to": _day(-1)}
    assert d["expense_k"] == -5000
    assert d["prev"]["expense_k"] == -4000
    assert d["avg_per_day_k"] == -5000


def test_pending_count(store):
    _add(store, _day(-1), -10000, merchant="X")
    store.conn.execute("UPDATE transactions SET review_status='pending'")
    store.conn.commit()

    assert build_digest(store, days=7, today=TODAY)["pending_count"] == 1


# ── Рекурринги ──────────────────────────────────────────────────────────────

def _monthly(store, merchant: str, kopecks: int, days: list[int],
             category: str = "subscriptions") -> None:
    for offset in days:
        _add(store, _day(offset), kopecks, category, merchant=merchant)


def test_upcoming_subscription_within_horizon(store):
    _monthly(store, "NETFLIX", -19900, [-95, -65, -35])
    _monthly(store, "СТАРАЯ", -9900, [-300, -270, -240])

    d = build_digest(store, days=7, today=TODAY)

    assert [u["merchant"] for u in d["upcoming"]] == ["NETFLIX"]
    assert d["upcoming"][0]["price_k"] == 19900
    assert d["upcoming"][0]["days_until"] == -5  # ожидалось today-5, активна (≤40 дн)


def test_subscription_beyond_horizon_not_listed(store):
    _monthly(store, "NETFLIX", -19900, [-120, -90, -60])

    d = build_digest(store, days=7, today=TODAY)

    assert d["upcoming"] == []


# ── Аномалии: крупная сумма ─────────────────────────────────────────────────

def _category_history(store, kopecks: int = -10000, n: int = 10,
                      category: str = "groceries") -> None:
    for i in range(n):
        _add(store, _day(-88 + i * 8), kopecks, category, merchant=f"МАГАЗИН {i}")


def test_large_expense_flagged(store):
    _category_history(store)
    _add(store, _day(-2), -150000, merchant="ТЕХНОГИГАНТ")

    d = build_digest(store, days=7, today=TODAY)

    anomalies = [a for a in d["anomalies"] if a["type"] == "large_expense"]
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a["merchant"] == "ТЕХНОГИГАНТ" and a["category"] == "groceries"
    assert a["amount_k"] == -150000
    assert a["median_k"] == 10000 and a["score"] == 15.0
    # суммы в детали — в отображаемой форме со знаком расхода (медиана — магнитуда)
    assert "\u22121500.00 ₽" in a["detail"]
    assert "\u2212100.00 ₽" in a["detail"]


def test_large_expense_needs_observations(store):
    _category_history(store, n=8)
    _add(store, _day(-2), -150000, merchant="ТЕХНОГИГАНТ")  # всего 9 наблюдений

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "large_expense"] == []


def test_large_expense_floor_ignores_small(store):
    _category_history(store, kopecks=-100, n=10)
    _add(store, _day(-2), -5000, merchant="МЕЛОЧЬ")  # ×50, но ниже пола 1000 ₽

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "large_expense"] == []


def test_large_expense_outside_window_not_flagged(store):
    _category_history(store)
    _add(store, _day(-20), -150000, merchant="ПРОШЛОЕ")

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "large_expense"] == []


# ── Аномалии: скачок цены рекурринга ────────────────────────────────────────

def test_price_jump_flagged(store):
    _monthly(store, "NETFLIX", -19900, [-95, -65, -35])
    _add(store, _day(-2), -29900, "subscriptions", merchant="NETFLIX")

    d = build_digest(store, days=7, today=TODAY)

    jumps = [a for a in d["anomalies"] if a["type"] == "price_jump"]
    assert len(jumps) == 1
    a = jumps[0]
    assert a["merchant"] == "NETFLIX"
    assert a["prev_price_k"] == 19900 and a["amount_k"] == -29900
    assert a["score"] == 1.5 and "+50%" in a["detail"]
    # и старая, и новая цена — с знаком расхода, без ложного «+» (демо-смоук 21.09)
    assert "\u2212299.00 ₽" in a["detail"] and "\u2212199.00 ₽" in a["detail"]


def test_price_jump_within_tolerance_not_flagged(store):
    _monthly(store, "NETFLIX", -19900, [-95, -65, -35])
    _add(store, _day(-2), -20900, "subscriptions", merchant="NETFLIX")  # +5.03%

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "price_jump"] == []


def test_price_jump_after_small_deviation(store):
    """Мягкое +8% (не скачок, но и не кластер) не должно маскировать последующий +30%."""
    _monthly(store, "NETFLIX", -19900, [-95, -65, -35])
    _add(store, _day(-30), -21500, "subscriptions", merchant="NETFLIX")
    _add(store, _day(-2), -25900, "subscriptions", merchant="NETFLIX")

    d = build_digest(store, days=7, today=TODAY)

    jumps = [a for a in d["anomalies"] if a["type"] == "price_jump"]
    assert len(jumps) == 1
    assert jumps[0]["amount_k"] == -25900 and jumps[0]["prev_price_k"] == 19900


def test_price_jump_exact_10_percent_boundary(store):
    """Ровно +10% — скачок (порог включительный)."""
    _monthly(store, "NETFLIX", -19900, [-95, -65, -35])
    _add(store, _day(-2), -21890, "subscriptions", merchant="NETFLIX")  # 19900 × 1.10

    d = build_digest(store, days=7, today=TODAY)

    jumps = [a for a in d["anomalies"] if a["type"] == "price_jump"]
    assert len(jumps) == 1 and jumps[0]["score"] == 1.1


def test_price_jump_first_deviation_outside_window_not_refetched(store):
    """Смена цены вне окна — не новость этой недели, в окне не флагуем (нет повторов)."""
    _monthly(store, "NETFLIX", -19900, [-95, -65, -35])
    _add(store, _day(-20), -25900, "subscriptions", merchant="NETFLIX")  # событие вне окна
    _add(store, _day(-2), -25900, "subscriptions", merchant="NETFLIX")   # та же новая цена

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "price_jump"] == []


def test_price_jump_requires_active_subscription(store):
    _monthly(store, "NETFLIX", -19900, [-125, -95, -65])  # нет списаний 65 дн
    _add(store, _day(-2), -29900, "subscriptions", merchant="NETFLIX")

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "price_jump"] == []


# ── Аномалии: near-дубли ────────────────────────────────────────────────────

def test_near_duplicate_flagged(store):
    _add(store, _day(-2), -30000, "restaurants", merchant="КОФЕ", desc="КОФЕ")
    _add(store, _day(-2), -30000, "restaurants", merchant="КОФЕ", desc="КОФЕ УГЛОВОЕ")

    d = build_digest(store, days=7, today=TODAY)

    dupes = [a for a in d["anomalies"] if a["type"] == "near_duplicate"]
    assert len(dupes) == 1
    assert dupes[0]["merchant"] == "КОФЕ" and dupes[0]["count"] == 2
    assert dupes[0]["amount_k"] == -30000 and dupes[0]["score"] == 2.0


def test_near_duplicate_different_amounts_not_flagged(store):
    _add(store, _day(-2), -30000, "restaurants", merchant="КОФЕ", desc="КОФЕ")
    _add(store, _day(-2), -40000, "restaurants", merchant="КОФЕ", desc="КОФЕ2")

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "near_duplicate"] == []


def test_near_duplicate_outside_window_not_flagged(store):
    _add(store, _day(-10), -30000, "restaurants", merchant="КОФЕ", desc="КОФЕ")
    _add(store, _day(-10), -30000, "restaurants", merchant="КОФЕ", desc="КОФЕ2")

    d = build_digest(store, days=7, today=TODAY)

    assert [a for a in d["anomalies"] if a["type"] == "near_duplicate"] == []


def test_anomalies_limited_and_sorted(store):
    for i in range(12):
        day = _day(-1 - i % 5)
        _add(store, day, -30000, "restaurants", merchant=f"КАФЕ {i}", desc=f"КАФЕ {i}")
        _add(store, day, -30000, "restaurants", merchant=f"КАФЕ {i}", desc=f"КАФЕ {i} ФИЛИАЛ")

    d = build_digest(store, days=7, today=TODAY)

    assert len(d["anomalies"]) == 10
    assert all(a["type"] == "near_duplicate" for a in d["anomalies"])


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_cli_digest_table_and_json(monkeypatch, capsys, store):
    base = datetime.now(UTC).date()
    _add(store, (base - timedelta(days=1)).isoformat(), -15000)
    _add(store, (base - timedelta(days=2)).isoformat(), 50000, "income")
    monkeypatch.setattr(cli, "make_store", lambda: store)

    assert cli.main(["digest"]) == 0
    out = capsys.readouterr().out
    assert "Дайджест" in out and "(7 дн)" in out
    assert "-150.00" in out and "500.00" in out
    assert "groceries" in out

    assert cli.main(["digest", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["period"]["days"] == 7
    assert payload["expense_k"] == -15000
    assert payload["income_k"] == 50000
    assert payload["top_categories"][0]["category"] == "groceries"


def test_cli_digest_overdue_label(monkeypatch, capsys, store):
    """Просроченное ожидаемое списание печатается как «просрочено», а не «через -N дн»."""
    base = datetime.now(UTC).date()
    for offset in (-95, -65, -35):
        _add(store, (base + timedelta(days=offset)).isoformat(), -19900,
             "subscriptions", merchant="NETFLIX")
    monkeypatch.setattr(cli, "make_store", lambda: store)

    assert cli.main(["digest"]) == 0
    out = capsys.readouterr().out
    assert "NETFLIX" in out and "просрочено на 5 дн" in out


def test_cli_digest_days_flag(monkeypatch, capsys, store):
    base = datetime.now(UTC).date()
    _add(store, (base - timedelta(days=20)).isoformat(), -99000)
    monkeypatch.setattr(cli, "make_store", lambda: store)
    capsys.readouterr()  # сброс вывода фикстуры (DB=...)

    assert cli.main(["digest", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["expense_k"] == 0

    assert cli.main(["digest", "--days", "30", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["expense_k"] == -99000
