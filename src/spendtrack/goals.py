"""Цели/копилки: представление (Ф1) + детерминированный движок (Ф2).

«Виртуальный конверт»: взносы — учёт намерения, деньги на счетах не блокируются; прогресс
и метрики считаются на лету (derived не храним, см. spec/ARCHITECTURE.md).

Движок (Ф2, `RESEARCH_SAVINGS_GOALS_2026-10-03.md` §3 + адъюдикация 03.10):
- ряд полных месяцев (текущий исключён) в базовой валюте; `transfers` исключены; missing ≠ 0;
- покрытие месяца: `max(date) == конец месяца` ИЛИ ≥ 5 транзакций, иначе месяц исключается;
- capacity = медиана net; «слабый месяц» = min(net) (p10 → min, адъюдикация);
- required = ceil_div(need, periods); pace = медиана положительных взносов по месяцам;
- статусы нейтральные (без «провала»), советы — только дискреционные категории (флаг taxonomy),
  рекурринги исключены; не-базовая валюта цели — только прогресс (NO_CAPACITY_DATA).
"""
from __future__ import annotations

from datetime import date, timedelta

from spendtrack.config import base_currency
from spendtrack.recurring import detect_recurring
from spendtrack.reports import foreign_transactions_count
from spendtrack.store import Store, fmt_money, month_bounds
from spendtrack.taxonomy import Taxonomy, load_taxonomy

MONTHS_WINDOW = 6
MIN_USABLE_MONTHS = 3
MIN_MONTH_TX = 5           # альтернатива покрытию «последняя операция в последний день месяца»
MIN_WARN_SHARE = 0.2       # доля исключённых месяцев окна для предупреждения
ADVICE_PCTS = (5, 10, 15, 20, 25, 30)
ADVICE_MAX = 3

STATUS_LABELS = {
    "DONE": "цель набрана",
    "ON_TRACK": "в графике",
    "AHEAD": "с запасом",
    "BEHIND": "нужен темп выше",
    "AT_RISK": "темп выше обычного",
    "OVERDUE": "срок прошёл",
    "NO_DEADLINE": "без срока",
    "INSUFFICIENT_DATA": "мало истории",
    "NO_CAPACITY_DATA": "валюта цели — только прогресс",
}


# ---- арифметика (чистые функции) ----

def shift_month(month: str, delta: int) -> str:
    """«2026-09» ± N месяцев → «2026-08» (строка YYYY-MM)."""
    y, m = int(month[:4]), int(month[5:7])
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def months_between(a: str, b: str) -> int:
    """Сколько месяцев от «a» до «b» (может быть 0/отрицательным)."""
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))


def ceil_div(a: int, b: int) -> int:
    """Деление копеек вверх (не обещаем достижимость за счёт потерянной копейки)."""
    return -(-a // b)


def median_k(values: list[int]) -> int:
    """Медиана целых копеек; чётное число — среднее двух центральных с отбрасыванием вниз."""
    xs = sorted(values)
    mid = len(xs) // 2
    if not xs:
        return 0
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) // 2


# ---- сбор данных (DB → снимок) ----

def monthly_net_series(store: Store, months: int = MONTHS_WINDOW,
                       today: date | None = None) -> list[dict]:
    """Полные календарные месяцы (без текущего): income/expense/net в базовой валюте + покрытие."""
    ref = today or date.today()  # noqa: DTZ011 — локальная календарная дата (как в UI/CLI)
    base = base_currency()
    cur = ref.strftime("%Y-%m")
    out: list[dict] = []
    for k in range(1, months + 1):
        m = shift_month(cur, -k)
        start, end = month_bounds(m)
        last_day = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
        row = store.conn.execute(
            "SELECT COUNT(*) n, COALESCE(MAX(date), '') mx,"
            " COALESCE(SUM(CASE WHEN amount_kopecks > 0 THEN amount_kopecks END), 0) inc,"
            " COALESCE(SUM(CASE WHEN amount_kopecks < 0 THEN amount_kopecks END), 0) exp"
            " FROM transactions"
            " WHERE date >= ? AND date < ? AND category <> 'transfers'"
            " AND COALESCE(UPPER(NULLIF(currency, '')), ?) = ?",
            (start, end, base, base),
        ).fetchone()
        n = int(row["n"])
        usable = n > 0 and (row["mx"] == last_day or n >= MIN_MONTH_TX)
        out.append({"month": m, "income_k": int(row["inc"]), "expense_k": -int(row["exp"]),
                    "net_k": int(row["inc"]) + int(row["exp"]), "n": n, "usable": usable})
    return out


def robust_stats(series: list[dict]) -> dict:
    """Медиана net («обычный поток»), min как «слабый месяц», волатильность MAD/|median|."""
    usable = [m for m in series if m["usable"]]
    nets = [m["net_k"] for m in usable]
    cap = median_k(nets)
    mad = median_k([abs(x - cap) for x in nets])
    return {
        "usable": len(usable),
        "excluded": len(series) - len(usable),
        "capacity_k": cap,
        "weakest_k": min(nets) if nets else 0,
        "vol": (mad / max(1, abs(cap))) if nets else 0.0,
        "tx_total": sum(m["n"] for m in usable),
    }


def monthly_contrib_median(allocations: list[dict], today: date | None = None,
                           months: int = MONTHS_WINDOW) -> int:
    """pace: медиана положительных взносов по месяцам за окно (факт пользователя)."""
    ref = today or date.today()  # noqa: DTZ011
    floor_month = shift_month(ref.strftime("%Y-%m"), -months)
    sums: dict[str, int] = {}
    for a in allocations:
        amount = int(a["amount_kopecks"])
        if amount <= 0:
            continue
        m = str(a["date"])[:7]
        if m >= floor_month:
            sums[m] = sums.get(m, 0) + amount
    return median_k(list(sums.values()))


# ---- движок одной цели (чистая функция) ----

def goal_engine(goal: dict, allocations: list[dict], stats: dict, *,
                today: date | None = None) -> dict:
    """Статус/взнос/прогноз одной цели от снимка данных (чистая; БД не трогает)."""
    ref = today or date.today()  # noqa: DTZ011
    cur = ref.strftime("%Y-%m")
    target = int(goal["target_kopecks"])
    saved = sum(int(a["amount_kopecks"]) for a in allocations)
    need = max(0, target - saved)
    pct = 100 if need == 0 else max(0, min(99, saved * 100 // target))
    res = {
        "status": None, "status_label": "", "saved_k": saved, "need_k": need, "progress_pct": pct,
        "required_k": None, "gap_k": None, "projected_k": None, "months_at_pace": None,
        "new_due_month": None, "pace_k": monthly_contrib_median(allocations, ref),
        "capacity_k": stats["capacity_k"], "weakest_k": stats["weakest_k"],
        "usable_months": stats["usable"], "advice": [], "warnings": [],
    }
    if need == 0:
        res["status"] = "DONE"
    elif goal["currency"] != base_currency():
        res["status"] = "NO_CAPACITY_DATA"  # чужая валюта не смешивается с потоком базовой
    else:
        _engine_deadline(res, goal, stats, cur)
    res["status_label"] = STATUS_LABELS[res["status"]]
    return res


def _engine_deadline(res: dict, goal: dict, stats: dict, cur: str) -> None:
    """Ветка по сроку: OVERDUE / NO_DEADLINE / INSUFFICIENT_DATA / потоковые статусы."""
    need, pace = res["need_k"], res["pace_k"]
    due = goal["due_month"]
    periods = max(0, months_between(cur, due)) if due is not None else 0
    if due is not None:
        res["required_k"] = ceil_div(need, max(1, periods))
    if due is not None and due < cur:
        res["status"] = "OVERDUE"
        res["gap_k"] = need
    elif due is None:
        res["status"] = "NO_DEADLINE"
        _pace_forecast(res, need, pace, cur)
    elif stats["usable"] < MIN_USABLE_MONTHS:
        res["status"] = "INSUFFICIENT_DATA"
        _pace_forecast(res, need, pace, cur)
    else:
        _flow_status(res, need, pace, max(1, periods), stats, cur)


def _pace_forecast(res: dict, need: int, pace: int, cur: str) -> None:
    """Прогноз по темпу пользователя: месяцев до цели и сдвинутый срок (нейтрально, без угроз)."""
    if pace > 0:
        res["months_at_pace"] = ceil_div(need, pace)
        res["new_due_month"] = shift_month(cur, res["months_at_pace"])


def _flow_status(res: dict, need: int, pace: int, periods: int, stats: dict, cur: str) -> None:
    """Потоковые статусы: AT_RISK → BEHIND → AHEAD (запас ≥10%) → ON_TRACK."""
    cover = pace * periods
    res["projected_k"] = res["saved_k"] + cover
    res["gap_k"] = max(0, need - cover)
    _pace_forecast(res, need, pace, cur)
    required = res["required_k"] or 0
    if required > stats["capacity_k"] or required > stats["weakest_k"]:
        res["status"] = "AT_RISK"
    elif cover < need:
        res["status"] = "BEHIND"
    elif cover * 10 >= need * 11:
        res["status"] = "AHEAD"
    else:
        res["status"] = "ON_TRACK"


# ---- советы (шаблонные, без LLM) ----

def category_monthly_avgs(store: Store, *, months: int = MONTHS_WINDOW, today: date | None = None,
                          discretionary: set[str] | None = None,
                          exclude_merchants: set[str] | None = None) -> list[dict]:
    """Медианы месячных расходов по дискреционным категориям (рефанды уменьшают, пол 0).

    Медиана — по месяцам, где категория была активна (нулевые месяцы «не тратил вовсе» размывали
    бы совет; «missing ≠ 0» относится к net-ряду цели, здесь месяц без операций = 0 трат).
    """
    ref = today or date.today()  # noqa: DTZ011
    base = base_currency()
    cur = ref.strftime("%Y-%m")
    first = shift_month(cur, -months)
    start, end = month_bounds(first)[0], month_bounds(cur)[0]
    sql = ("SELECT substr(date, 1, 7) m, category, SUM(amount_kopecks) s FROM transactions"
           " WHERE date >= ? AND date < ? AND COALESCE(UPPER(NULLIF(currency, '')), ?) = ?")
    params: list[str] = [start, end, base, base]
    if exclude_merchants:
        marks = ",".join("?" * len(exclude_merchants))
        sql += f" AND UPPER(COALESCE(merchant, '')) NOT IN ({marks})"
        params.extend(sorted(exclude_merchants))
    sql += " GROUP BY m, category"
    by_cat: dict[str, dict[str, int]] = {}
    for r in store.conn.execute(sql, params).fetchall():
        spent = max(0, -int(r["s"]))  # рефанды уменьшают расход, ниже нуля не уходим
        by_cat.setdefault(r["category"], {})[r["m"]] = spent
    out: list[dict] = []
    for cat, per_month in by_cat.items():
        if discretionary is not None and cat not in discretionary:
            continue
        avg = median_k(list(per_month.values()))
        if avg > 0:
            out.append({"category": cat, "avg_k": avg})
    out.sort(key=lambda a: (-a["avg_k"], a["category"]))
    return out


def what_if(required_k: int, pace_k: int, avgs: list[dict]) -> list[dict]:
    """Варианты «сократить X на Y%»: сначала одиночные (щадящий %, затем сумма), затем пары ≤ 40%."""
    deficit = max(0, required_k - pace_k)
    if deficit <= 0 or not avgs:
        return []
    singles = _single_candidates(deficit, avgs)
    if singles:
        return singles[:ADVICE_MAX]
    return _pair_candidates(deficit, avgs)[:ADVICE_MAX]


def _single_candidates(deficit: int, avgs: list[dict]) -> list[dict]:
    singles: list[dict] = []
    for c in avgs:
        for y in ADVICE_PCTS:
            cover = c["avg_k"] * y // 100
            if cover >= deficit:
                singles.append({"items": [{"category": c["category"], "pct": y, "month_k": cover}],
                                "total_month_k": cover, "pct_sum": y})
                break
    singles.sort(key=lambda v: (v["pct_sum"], -v["total_month_k"]))
    return singles


def _pair_candidates(deficit: int, avgs: list[dict]) -> list[dict]:
    pairs: dict[tuple[str, str], dict] = {}
    top = avgs[:5]
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            found = _best_pair(deficit, a, b)
            if found:
                pairs[(a["category"], b["category"])] = found
    return sorted(pairs.values(), key=lambda v: (v["pct_sum"], -v["total_month_k"]))


def _best_pair(deficit: int, a: dict, b: dict) -> dict | None:
    found = None
    for y1 in ADVICE_PCTS:
        for y2 in ADVICE_PCTS:
            if y1 + y2 > 40:
                continue
            cover = a["avg_k"] * y1 // 100 + b["avg_k"] * y2 // 100
            if cover >= deficit and (
                    found is None or (y1 + y2, -cover) < (found["pct_sum"], -found["total_month_k"])):
                found = {"items": [{"category": a["category"], "pct": y1,
                                    "month_k": a["avg_k"] * y1 // 100},
                                   {"category": b["category"], "pct": y2,
                                    "month_k": b["avg_k"] * y2 // 100}],
                         "total_month_k": cover, "pct_sum": y1 + y2}
    return found


# ---- сборка: план цели + снимок страницы ----

def _recurring_merchants(store: Store, ref: date) -> set[str]:
    return {str(s["merchant"]).upper() for s in detect_recurring(store, ref) if s["active"]}


def goal_plan(store: Store, goal: dict, series: list[dict], stats: dict, *,
              today: date | None = None, taxonomy: Taxonomy | None = None,
              recurring_merchants: set[str] | None = None) -> dict:
    """Движок + предупреждения + советы для одной цели (общие снимки передаются снаружи)."""
    ref = today or date.today()  # noqa: DTZ011
    allocations = store.list_allocations(int(goal["id"]))
    res = goal_engine(goal, allocations, stats, today=ref)
    window = series
    if stats["excluded"] and stats["excluded"] / max(1, len(window)) > MIN_WARN_SHARE:
        res["warnings"].append({
            "code": "skipped_months",
            "text": f"В {stats['excluded']} мес окна мало данных — оценка может быть смещена"})
    if stats["usable"] < MIN_USABLE_MONTHS:
        res["warnings"].append({
            "code": "insufficient_history",
            "text": f"Мало истории ({stats['usable']} полн. мес) — прогноз пока грубый"})
    if res["status"] == "BEHIND":
        res["warnings"].append({
            "code": "goal_gap",
            "text": f"При текущем темпе не хватает {fmt_money(res['gap_k'], signed=False)}"})
    if res["status"] == "AT_RISK":
        res["warnings"].append({
            "code": "required_above_flow",
            "text": "Нужный взнос выше обычного месячного потока — темп придётся поднять"})
    if res["status"] in {"BEHIND", "AT_RISK"} and res["required_k"]:
        taxonomy = taxonomy or load_taxonomy()
        discretionary = {c.name for c in taxonomy.categories if c.discretionary}
        merchants = recurring_merchants if recurring_merchants is not None else _recurring_merchants(store, ref)
        avgs = category_monthly_avgs(store, today=ref, discretionary=discretionary,
                                     exclude_merchants=merchants)
        res["advice"] = what_if(res["required_k"], res["pace_k"], avgs)
    pending = store.pending_count()
    if pending:
        res["warnings"].append({
            "code": "pending_queue",
            "text": f"{pending} операций в очереди — категории могут измениться"})
    start, end = month_bounds(shift_month(ref.strftime("%Y-%m"), -len(window)))[0], \
        month_bounds(ref.strftime("%Y-%m"))[0]
    foreign = foreign_transactions_count(store, start, end)
    if foreign:
        res["warnings"].append({
            "code": "foreign_excluded",
            "text": f"{foreign} операций в валюте не учтены в оценке"})
    return res


def goals_overview(store: Store, include_archived: bool = False) -> list[dict]:
    """Список целей с прогрессом: pct (0..100), allocated/remaining, взносы (журнал)."""
    out: list[dict] = []
    for goal in store.list_goals(include_archived=include_archived):
        gid = int(goal["id"])
        prog = store.goal_progress(gid)
        target, allocated = int(prog["target_kopecks"]), int(prog["allocated_kopecks"])
        if prog["done"]:
            pct = 100
        else:
            pct = max(0, min(99, allocated * 100 // target)) if target else 0
        out.append({
            "id": gid,
            "title": goal["title"],
            "currency": goal["currency"],
            "target_kopecks": target,
            "allocated_kopecks": allocated,
            "remaining_kopecks": int(prog["remaining_kopecks"]),
            "allocations_count": int(prog["allocations"]),
            "done": bool(prog["done"]),
            "pct": pct,
            "due_month": goal["due_month"],
            "created_month": goal["created_month"],
            "archived": int(goal["archived"]),
            "allocations": store.list_allocations(gid),
        })
    return out


def goals_snapshot(store: Store, *, today: date | None = None) -> dict:
    """Контекст страницы/фрагмента: активные (+ планы Ф2) + архивные + портфельное предупреждение."""
    ref = today or date.today()  # noqa: DTZ011
    series = monthly_net_series(store, today=ref)
    stats = robust_stats(series)
    taxonomy = load_taxonomy()
    merchants = _recurring_merchants(store, ref)
    all_goals = goals_overview(store, include_archived=True)
    active = [g for g in all_goals if not g["archived"]]
    for g in active:
        g["plan"] = goal_plan(store, g, series, stats, today=ref,
                              taxonomy=taxonomy, recurring_merchants=merchants)
    base = base_currency()
    total_saved = sum(g["allocated_kopecks"] for g in active if g["currency"] == base)
    net_window = max(0, sum(m["net_k"] for m in series if m["usable"]))
    portfolio_warning = None
    if total_saved > net_window:
        portfolio_warning = (
            f"Сумма меток ({fmt_money(total_saved, signed=False)}) больше свободного потока за "
            f"{stats['usable']} полн. мес — проверьте, что это посильно.")
    return {
        "goals": active,
        "archived": [g for g in all_goals if g["archived"]],
        "today": ref.isoformat(),
        "usable_months": stats["usable"],
        "portfolio_warning": portfolio_warning,
        "catname": taxonomy.display,
    }
