"""Ф2 движка целей: юнит-матрица границ (чистые функции) + снимки БД (оффлайн).

Формулы — RESEARCH_SAVINGS_GOALS_2026-10-03.md §3 + адъюдикация 03.10 (p10→min, required вверх,
AHEAD ≥ 1.1×, не-базовая валюта — только прогресс, флаг discretionary в taxonomy).
"""
from __future__ import annotations

from datetime import date

from spendtrack import goals as G
from spendtrack.store import Store

TODAY = date(2026, 10, 3)


def _stats(usable: int = 6, cap: int = 200_000, weak: int = 130_000) -> dict:
    return {"usable": usable, "excluded": 0, "capacity_k": cap, "weakest_k": weak,
            "vol": 0.0, "tx_total": 100}


def _goal(target: int = 1_000_000, due: str | None = "2027-06", currency: str = "RUB") -> dict:
    return {"id": 1, "title": "Цель", "target_kopecks": target, "due_month": due,
            "currency": currency}


def _alloc(day: str, amount: int) -> dict:
    return {"date": day, "amount_kopecks": amount}


def _add(store: Store, day: str, kopecks: int, category: str = "groceries",
         merchant: str | None = None) -> None:
    store.add_transaction(date=day, description="ТЕСТ", amount_kopecks=kopecks,
                          category=category, category_source="rule", merchant=merchant)


# ---- арифметика ----

def test_shift_between_ceil_median():
    assert G.shift_month("2026-01", -1) == "2025-12"
    assert G.shift_month("2026-12", 1) == "2027-01"
    assert G.months_between("2026-10", "2027-06") == 8
    assert G.months_between("2026-10", "2026-10") == 0
    assert G.ceil_div(1, 8) == 1 and G.ceil_div(16, 8) == 2 and G.ceil_div(17, 8) == 3
    assert G.median_k([]) == 0 and G.median_k([5]) == 5
    assert G.median_k([1, 3, 5, 7]) == 4 and G.median_k([-3, -1, 5]) == -1


# ---- статусы (чистые) ----

def test_done_overdue_no_deadline():
    done = G.goal_engine(_goal(target=1000), [_alloc("2026-09-01", 1000)], _stats(), today=TODAY)
    assert done["status"] == "DONE" and done["progress_pct"] == 100
    over = G.goal_engine(_goal(due="2026-08"), [], _stats(), today=TODAY)
    assert over["status"] == "OVERDUE" and over["gap_k"] == 1_000_000
    nd = G.goal_engine(_goal(due=None), [_alloc("2026-09-05", 100_000)], _stats(), today=TODAY)
    assert nd["status"] == "NO_DEADLINE" and nd["months_at_pace"] == 9  # need 900к / pace 100к
    assert G.goal_engine(_goal(due=None), [], _stats(), today=TODAY)["months_at_pace"] is None


def test_status_matrix_on_track_ahead_behind_at_risk():
    g = _goal()  # взнос входит и в saved: A=115к → need 885к, required 110 625, pace 115к
    on_track = G.goal_engine(g, [_alloc("2026-09-05", 115_000)], _stats(), today=TODAY)
    assert on_track["status"] == "ON_TRACK" and on_track["required_k"] == 110_625
    ahead = G.goal_engine(g, [_alloc("2026-09-05", 130_000)], _stats(), today=TODAY)
    assert ahead["status"] == "AHEAD"  # cover 1 040 000 ≥ 1.1× need 957 000
    behind = G.goal_engine(g, [_alloc("2026-09-05", 50_000)], _stats(), today=TODAY)
    assert behind["status"] == "BEHIND" and behind["gap_k"] == 550_000  # need 950к − cover 400к
    at_risk = G.goal_engine(g, [_alloc("2026-09-05", 50_000)],
                            _stats(weak=100_000), today=TODAY)
    assert at_risk["status"] == "AT_RISK"  # required 118 750 > слабый месяц 100 000


def test_required_boundaries():
    # due = текущий месяц → весь остаток в этот месяц
    cur = G.goal_engine(_goal(target=10_000, due="2026-10"), [], _stats(), today=TODAY)
    assert cur["required_k"] == 10_000
    # 12 периодов
    year = G.goal_engine(_goal(target=1_200_000, due="2027-10"), [], _stats(), today=TODAY)
    assert year["required_k"] == 100_000
    # нехватка в 1 копейку — взнос всё равно ≥ 1
    one = G.goal_engine(_goal(target=1000), [_alloc("2026-09-01", 999)], _stats(), today=TODAY)
    assert one["need_k"] == 1 and one["required_k"] == 1


def test_insufficient_and_non_base():
    insuff = G.goal_engine(_goal(), [], _stats(usable=2), today=TODAY)
    assert insuff["status"] == "INSUFFICIENT_DATA"
    usd = G.goal_engine(_goal(currency="USD"), [_alloc("2026-09-01", 500)], _stats(), today=TODAY)
    assert usd["status"] == "NO_CAPACITY_DATA" and usd["required_k"] is None and usd["advice"] == []


# ---- what-if (чистые) ----

def test_what_if_singles_and_pairs():
    avgs = [{"category": "groceries", "avg_k": 300_000}, {"category": "restaurants", "avg_k": 200_000}]
    singles = G.what_if(required_k=100_000, pace_k=80_000, avgs=avgs)  # дефицит 20 000
    assert singles and singles[0]["items"][0] == {"category": "groceries", "pct": 10, "month_k": 30_000}
    pairs = G.what_if(required_k=150_000, pace_k=0,
                      avgs=[{"category": "groceries", "avg_k": 400_000},
                            {"category": "restaurants", "avg_k": 300_000}])
    assert pairs and len(pairs[0]["items"]) == 2 and pairs[0]["total_month_k"] >= 150_000
    assert G.what_if(100_000, 100_000, avgs) == []  # дефицита нет — советов нет


# ---- снимки БД ----

def test_series_coverage_and_transfers(store):
    _add(store, "2026-09-30", -10_000)   # конец месяца → usable
    _add(store, "2026-08-15", -5_000)    # 1 транзакция в середине → исключён
    _add(store, "2026-07-01", 100_000, category="transfers")  # transfers не считаем вовсе
    series = G.monthly_net_series(store, today=TODAY)
    by = {m["month"]: m for m in series}
    assert by["2026-09"]["usable"] and by["2026-09"]["net_k"] == -10_000
    assert not by["2026-08"]["usable"]
    assert by["2026-07"]["n"] == 0
    stats = G.robust_stats(series)
    assert stats["usable"] == 1 and stats["capacity_k"] == -10_000 and stats["excluded"] == 5


def test_category_avgs_refunds_floor_and_median(store):
    _add(store, "2026-09-10", -30_000)                 # сентябрь: 30к расход
    _add(store, "2026-09-12", 10_000)                  #   рефанд −10к → 20к
    _add(store, "2026-08-10", -50_000)                 # август: 50к
    _add(store, "2026-07-05", -10_000, category="restaurants")
    _add(store, "2026-07-06", 15_000, category="restaurants")  # рефанд больше → пол 0 → без совета
    _add(store, "2026-09-11", -20_000, category="housing")     # не дискреционная
    avgs = G.category_monthly_avgs(store, today=TODAY, discretionary={"groceries", "restaurants"})
    assert [(a["category"], a["avg_k"]) for a in avgs] == [("groceries", 35_000)]


def test_category_avgs_excludes_recurring_merchants(store):
    _add(store, "2026-09-10", -30_000, category="subscriptions", merchant="NETFLIX")
    _add(store, "2026-09-11", -20_000, category="subscriptions", merchant="OKKO")
    avgs = G.category_monthly_avgs(store, today=TODAY, discretionary={"subscriptions"},
                                   exclude_merchants={"NETFLIX"})
    assert [(a["category"], a["avg_k"]) for a in avgs] == [("subscriptions", 20_000)]


def _seed_full_months(store: Store) -> None:
    for day in ("2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"):
        _add(store, day, 200_000, category="income")


def test_snapshot_plans_portfolio_warning_and_queue(store):
    _seed_full_months(store)
    gid = store.add_goal("Подушка", 1_000_000, due_month="2027-06")
    store.add_allocation(gid, "2026-09-20", 1_300_000)  # набрано больше потока окна (1.2M)
    store.add_goal("Отпуск", 500_000, due_month="2027-06")
    _add(store, "2026-09-15", -1_000)  # останется pending ниже
    store.conn.execute("UPDATE transactions SET review_status='pending' WHERE id=(SELECT MAX(id) FROM transactions)")
    store.conn.commit()

    snap = G.goals_snapshot(store, today=TODAY)
    assert snap["usable_months"] == 6
    done, behind = snap["goals"]
    assert done["plan"]["status"] == "DONE" and done["plan"]["status_label"] == "цель набрана"
    assert behind["plan"]["status"] == "BEHIND" and behind["plan"]["status_label"] == "нужен темп выше"
    codes = {w["code"] for w in behind["plan"]["warnings"]}
    assert "pending_queue" in codes and "goal_gap" in codes
    assert snap["portfolio_warning"] and "Сумма меток" in snap["portfolio_warning"]


def test_snapshot_insufficient_history_warning(store):
    _add(store, "2026-09-30", 100_000, category="income")  # один usable месяц
    store.add_goal("Цель", 100_000, due_month="2027-06")
    snap = G.goals_snapshot(store, today=TODAY)
    plan = snap["goals"][0]["plan"]
    assert plan["status"] == "INSUFFICIENT_DATA"
    assert any(w["code"] == "insufficient_history" for w in plan["warnings"])
