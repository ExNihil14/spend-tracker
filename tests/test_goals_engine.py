"""Ф2 движка целей: юнит-матрица границ (чистые функции) + снимки БД (оффлайн).

Формулы — RESEARCH_SAVINGS_GOALS_2026-10-03.md §3 + адъюдикация 03.10 (p10→min, required вверх,
AHEAD ≥ 1.1×, не-базовая валюта — только прогресс, флаг discretionary в taxonomy).
"""
from __future__ import annotations

from datetime import date

import pytest

from spendtrack import goals as G
from spendtrack.store import Store

TODAY = date(2026, 10, 3)


def _stats(usable: int = 6, cap: int = 200_000, weak: int = 130_000) -> dict:
    return {"usable": usable, "excluded": 0, "capacity_k": cap, "weakest_k": weak,
            "vol": 0.0, "tx_total": 100}


def _goal(target: int = 1_000_000, due: str | None = "2027-06", currency: str = "RUB",
          created: str = "2026-09") -> dict:
    return {"id": 1, "title": "Цель", "target_kopecks": target, "due_month": due,
            "currency": currency, "created_month": created}


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
    assert G.months_between("2027-01", "2026-10") == -3  # срок в прошлом (wave5 S10)
    assert G.ceil_div(1, 8) == 1 and G.ceil_div(16, 8) == 2 and G.ceil_div(17, 8) == 3
    with pytest.raises(ZeroDivisionError):  # делитель защищает вызывающий (в движке — max(1, …))
        G.ceil_div(5, 0)
    assert G.median_k([]) == 0 and G.median_k([5]) == 5
    assert G.median_k([1, 3, 5, 7]) == 4 and G.median_k([-3, -1, 5]) == -1


# ---- статусы (чистые) ----

def test_done_overdue_no_deadline():
    done = G.goal_engine(_goal(target=1000), [_alloc("2026-09-01", 1000)], _stats(), today=TODAY)
    assert done["status"] == "DONE" and done["progress_pct"] == 100
    over = G.goal_engine(_goal(due="2026-08"), [], _stats(), today=TODAY)
    assert over["status"] == "OVERDUE" and over["gap_k"] == 1_000_000
    nd = G.goal_engine(_goal(due=None), [_alloc("2026-09-05", 100_000)], _stats(), today=TODAY)
    assert nd["status"] == "NO_DEADLINE" and nd["months_at_pace"] == 8  # остаток тек. месяца 100к + 8×100к
    assert G.goal_engine(_goal(due=None), [], _stats(), today=TODAY)["months_at_pace"] is None


def test_status_matrix_on_track_ahead_behind_at_risk():
    g = _goal()  # 9 периодов (окт..июн включительно); взнос входит и в saved
    on_track = G.goal_engine(g, [_alloc("2026-09-05", 105_000)], _stats(), today=TODAY)
    assert on_track["status"] == "ON_TRACK" and on_track["required_k"] == 99_445
    ahead = G.goal_engine(g, [_alloc("2026-09-05", 120_000)], _stats(), today=TODAY)
    assert ahead["status"] == "AHEAD"  # cover 1 080 000 ≥ 1.1× need 968 000
    behind = G.goal_engine(g, [_alloc("2026-09-05", 50_000)], _stats(), today=TODAY)
    assert behind["status"] == "BEHIND" and behind["gap_k"] == 500_000  # need 950к − cover 450к
    at_risk = G.goal_engine(g, [_alloc("2026-09-05", 50_000)],
                            _stats(weak=100_000), today=TODAY)
    assert at_risk["status"] == "AT_RISK"  # required 105 556 > слабый месяц 100 000


def test_required_boundaries():
    # due = текущий месяц → весь остаток в этот месяц
    cur = G.goal_engine(_goal(target=10_000, due="2026-10"), [], _stats(), today=TODAY)
    assert cur["required_k"] == 10_000
    # 12 месяцев до срока + текущий → 13 периодов
    year = G.goal_engine(_goal(target=1_200_000, due="2027-10"), [], _stats(), today=TODAY)
    assert year["required_k"] == 92_308
    # нехватка в 1 копейку — взнос всё равно ≥ 1
    one = G.goal_engine(_goal(target=1000), [_alloc("2026-09-01", 999)], _stats(), today=TODAY)
    assert one["need_k"] == 1 and one["required_k"] == 1


def test_engine_current_month_contribution_not_double_counted():
    """S3 (wave5): взнос текущего месяца уже в saved — cover не планирует ещё один полный (без ложного AHEAD)."""
    allocs = [_alloc("2026-09-10", 100_000), _alloc("2026-10-01", 100_000)]
    res = G.goal_engine(_goal(target=1_000_000), allocs, _stats(), today=TODAY)
    # saved 200к, need 800к; cover = 0 (остаток месяца) + 100к × 8 полных = 800к → ровно ON_TRACK
    assert res["cur_rest_k"] == 0 and res["projected_k"] == 1_000_000
    assert res["status"] == "ON_TRACK" and res["gap_k"] == 0
    assert res["months_at_pace"] == 8  # (800к − 0) / 100к — без сдвига на +1


def test_engine_forecast_keeps_current_month_available():
    """S3: если остаток текущего месяца покрывает нехватку — прогноз в ТЕКУЩЕМ месяце (было +1)."""
    res = G.goal_engine(_goal(target=1_000_000), [_alloc("2026-09-10", 900_000)], _stats(), today=TODAY)
    assert res["need_k"] == 100_000 and res["cur_rest_k"] == 900_000  # обычный темп месяца ещё не выбран
    assert res["months_at_pace"] == 0 and res["new_due_month"] == "2026-10"


def test_net_pace_counts_withdrawals_and_zero_months():
    """S4 (wave5): +100к/−100к ×6 → чистый темп 0 → ложный ON_TRACK исчезает."""
    allocs: list[dict] = []
    for m in ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"):
        allocs += [_alloc(f"{m}-05", 100_000), _alloc(f"{m}-20", -100_000)]
    res = G.goal_engine(_goal(created="2026-04"), allocs, _stats(), today=TODAY)
    assert res["pace_k"] == 0 and res["status"] == "BEHIND"


def test_net_pace_ignores_months_before_creation():
    """S4: месяцы до появления цели не размывают темп нулями (окно — от created_month)."""
    res = G.goal_engine(_goal(created="2026-09"), [_alloc("2026-09-05", 100_000)], _stats(), today=TODAY)
    assert res["pace_k"] == 100_000


def test_status_boundary_equalities():
    """Wave5 S10: равенства на границах — off-by-one не должен «съезжать»."""
    g = _goal()
    eq = G.goal_engine(g, [_alloc("2026-09-05", 100_000)], _stats(), today=TODAY)
    assert eq["status"] == "ON_TRACK" and eq["gap_k"] == 0  # cover == need (не BEHIND)
    # ровно 1.1×: target 1 010 000, взнос 110 000 → need 900к, cover 990к (990к×10 == 900к×11)
    ahead = G.goal_engine(_goal(target=1_010_000), [_alloc("2026-09-05", 110_000)],
                          _stats(), today=TODAY)
    assert ahead["status"] == "AHEAD"
    # required ровно равен слабому месяцу (130 000): строгий `>` не даёт AT_RISK
    eqw = G.goal_engine(_goal(target=1_170_000), [], _stats(), today=TODAY)
    assert eqw["required_k"] == 130_000 and eqw["status"] == "BEHIND"
    # pace = 0 со сроком: BEHIND, без прогноза темпа; required — округление вверх
    zero = G.goal_engine(g, [], _stats(), today=TODAY)
    assert zero["status"] == "BEHIND" and zero["months_at_pace"] is None
    assert zero["required_k"] == 111_112


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
    _add(store, "2026-10-01", -500_000)  # wave5 S11: текущий (неполный) месяц в окно не входит
    series = G.monthly_net_series(store, today=TODAY)
    by = {m["month"]: m for m in series}
    assert "2026-10" not in by  # серия — только полные календарные месяцы
    assert by["2026-09"]["usable"] and by["2026-09"]["net_k"] == -10_000
    assert not by["2026-08"]["usable"]
    assert by["2026-07"]["n"] == 0
    stats = G.robust_stats(series)
    assert stats["usable"] == 1 and stats["capacity_k"] == -10_000 and stats["excluded"] == 5


def test_category_avgs_refunds_floor_and_average(store):
    _add(store, "2026-09-10", -30_000)                 # сентябрь: 30к расход
    _add(store, "2026-09-12", 10_000)                  #   рефанд −10к → 20к
    _add(store, "2026-08-10", -50_000)                 # август: 50к
    _add(store, "2026-07-05", -10_000, category="restaurants")
    _add(store, "2026-07-06", 15_000, category="restaurants")  # рефанд больше → пол 0
    _add(store, "2026-09-11", -20_000, category="housing")     # не дискреционная
    # wave5 S5: база — среднее по пригодным месяцам (авг+сен), нули/рефанды корректны
    avgs = G.category_monthly_avgs(store, today=TODAY, discretionary={"groceries", "restaurants"},
                                   usable_months={"2026-08", "2026-09"})
    assert [(a["category"], a["avg_k"]) for a in avgs] == [("groceries", 35_000)]
    assert "restaurants" not in [a["category"] for a in avgs]  # июль вне пригодных месяцев → база 0


def test_category_avgs_excludes_recurring_merchants(store):
    _add(store, "2026-09-10", -30_000, category="subscriptions", merchant="NETFLIX")
    _add(store, "2026-09-11", -20_000, category="subscriptions", merchant="OKKO")
    avgs = G.category_monthly_avgs(store, today=TODAY, discretionary={"subscriptions"},
                                   exclude_merchants={"NETFLIX"}, usable_months={"2026-09"})
    assert [(a["category"], a["avg_k"]) for a in avgs] == [("subscriptions", 20_000)]


def test_category_avgs_zero_fill_over_usable_months(store):
    """S5 (wave5): разовый расход 120к в одном из 6 пригодных месяцев → база 20к/мес, не 120к."""
    _add(store, "2026-09-10", -120_000, category="travel")
    usable = {"2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"}
    avgs = G.category_monthly_avgs(store, today=TODAY, discretionary={"travel"}, usable_months=usable)
    assert [(a["category"], a["avg_k"]) for a in avgs] == [("travel", 20_000)]


def test_category_avgs_no_base_without_usable_months(store):
    """S5: нет пригодных месяцев — честной базы нет (goal_plan в этом случае даёт insufficient_history)."""
    _add(store, "2026-09-10", -120_000, category="travel")
    assert G.category_monthly_avgs(store, today=TODAY, discretionary={"travel"}, usable_months=set()) == []


def test_what_if_uses_flow_capacity():
    """S6 (wave5): дефицит совета учитывает и поток (capacity): при отрицательном — сокращение больше."""
    avgs = [{"category": "groceries", "avg_k": 1_000_000}]
    assert G.what_if(100_000, 0, avgs)[0]["items"][0]["pct"] == 10          # дефицит 100к
    assert G.what_if(100_000, 0, avgs, capacity_k=-50_000)[0]["items"][0]["pct"] == 15  # 100к + 50к


def test_what_if_uses_floor_for_residual_deficit():
    """wave6_ui should: остаточный дефицит на период (floor) учитывается, даже когда base ≤ 0."""
    avgs = [{"category": "groceries", "avg_k": 1_000_000}]
    assert G.what_if(50_000, 100_000, avgs, capacity_k=100_000) == []  # base 0 → советов нет
    advice = G.what_if(50_000, 100_000, avgs, capacity_k=100_000, floor_k=50_000)
    assert advice and advice[0]["items"][0]["pct"] == 5  # 5% × 1 000 000 ≥ 50 000


def test_goal_plan_advice_when_current_month_already_paid(store):
    """wave6_ui should (сценарий ревью): взнос текущего месяца уже в saved — совет всё равно строится."""
    from spendtrack.taxonomy import Category, Taxonomy

    for day in ("2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"):
        _add(store, day, 1_000_000, category="income")
        _add(store, day, -300_000, category="groceries")
    gid = store.add_goal("Цель", 250_000, due_month="2026-10")  # срок — текущий месяц
    store.conn.execute("UPDATE goals SET created_month='2026-09' WHERE id=?", (gid,))
    store.conn.commit()
    store.add_allocation(gid, "2026-09-10", 100_000)
    store.add_allocation(gid, "2026-10-01", 100_000)  # текущий месяц уже оплачен
    series = G.monthly_net_series(store, today=TODAY)
    stats = G.robust_stats(series)
    tax = Taxonomy([Category("groceries", "#000", discretionary=True),
                    Category("income", "#000", discretionary=False)], [])
    plan = G.goal_plan(store, store.list_goals()[0], series, stats, today=TODAY,
                       taxonomy=tax, recurring_merchants=set())
    assert plan["need_k"] == 50_000 and plan["cur_rest_k"] == 0
    assert plan["status"] == "BEHIND"
    assert plan["advice"], "floor = ceil(gap/periods) = 50 000 — совет обязан построиться"


def test_goal_plan_warns_flow_deficit(store):
    """S6: при отрицательном потоке советов может не быть, но предупреждение о кассовом дефиците — есть."""
    from spendtrack.taxonomy import Category, Taxonomy

    for day in ("2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"):
        _add(store, day, 200_000, category="income")
        _add(store, day, -400_000, category="groceries")
    store.add_goal("Цель", 1_000_000, due_month="2027-06")
    series = G.monthly_net_series(store, today=TODAY)
    stats = G.robust_stats(series)
    assert stats["capacity_k"] < 0
    tax = Taxonomy([Category("groceries", "#000", discretionary=True),
                    Category("income", "#000", discretionary=False)], [])
    goal = store.list_goals()[0]
    plan = G.goal_plan(store, goal, series, stats, today=TODAY, taxonomy=tax, recurring_merchants=set())
    assert plan["status"] == "AT_RISK"
    assert any(w["code"] == "flow_deficit" for w in plan["warnings"])  # сокращения не создают деньги


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
    assert snap["portfolio_warning"] and "Взносы за последние" in snap["portfolio_warning"]


def test_snapshot_insufficient_history_warning(store):
    _add(store, "2026-09-30", 100_000, category="income")  # один usable месяц
    store.add_goal("Цель", 100_000, due_month="2027-06")
    snap = G.goals_snapshot(store, today=TODAY)
    plan = snap["goals"][0]["plan"]
    assert plan["status"] == "INSUFFICIENT_DATA"
    assert any(w["code"] == "insufficient_history" for w in plan["warnings"])


def test_discretionary_fallback_for_old_taxonomy():
    """Ревью wave5 S8: старые установки без флагов получают встроенный дефолт (советы не выключены)."""
    from spendtrack.taxonomy import Category, Taxonomy

    old = Taxonomy([Category("groceries", "#000"), Category("housing", "#000"),
                    Category("transfers", "#000")], [])
    names = G.discretionary_names(old)
    assert "groceries" in names and "housing" not in names and "transfers" not in names

    flagged = Taxonomy([Category("groceries", "#000", discretionary=True),
                        Category("housing", "#000", discretionary=False)], [])
    assert G.discretionary_names(flagged) == {"groceries"}


def test_discretionary_flags_distinguish_absent_from_false():
    """S1 (wave5): явные all-false НЕ включают fallback; legacy-дефолт не советует health/education."""
    from spendtrack.taxonomy import Category, Taxonomy

    all_false = Taxonomy([Category("groceries", "#000", discretionary=False),
                          Category("health", "#000", discretionary=False)], [])
    assert G.discretionary_names(all_false) == set()  # советы выключены явно (не «нет флагов»)

    old = Taxonomy([Category("groceries", "#000"), Category("health", "#000"),
                    Category("education", "#000"), Category("housing", "#000"),
                    Category("restaurants", "#000")], [])
    assert G.discretionary_names(old) == {"groceries", "restaurants"}  # здоровье/учёба не режем


def test_portfolio_warning_uses_same_usable_months(store):
    """S2 (wave5): взносы сравниваются с потоком по ОДНОМУ набору месяцев — начало окна не теряется."""
    _seed_full_months(store)  # апрель–сентябрь, поток +1.2M
    gid = store.add_goal("Цель", 5_000_000)
    store.add_allocation(gid, "2026-08-15", 1_300_000)  # август: раньше молча пропускался
    snap = G.goals_snapshot(store, today=TODAY)
    assert snap["portfolio_warning"] and "Взносы" in snap["portfolio_warning"]


def test_portfolio_warning_excludes_current_month(store):
    """S2: взнос текущего месяца (окно неполное) не считается против полного потока."""
    _seed_full_months(store)  # поток по полным месяцам = 1.2M
    gid = store.add_goal("Цель", 5_000_000)
    store.add_allocation(gid, "2026-10-01", 2_000_000)  # текущий месяц
    snap = G.goals_snapshot(store, today=TODAY)
    assert snap["portfolio_warning"] is None
