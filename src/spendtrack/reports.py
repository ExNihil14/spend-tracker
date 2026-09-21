from __future__ import annotations

from spendtrack.store import Store


def report_month(store: Store, month: str) -> dict:
    rows = store.conn.execute(
        "SELECT category, SUM(amount_kopecks) AS total_k, COUNT(*) AS n"
        " FROM transactions WHERE substr(date,1,7)=? AND currency='RUB' GROUP BY category ORDER BY total_k",
        (month,),
    ).fetchall()
    income = sum(r["total_k"] for r in rows if r["total_k"] > 0)
    expense = sum(r["total_k"] for r in rows if r["total_k"] < 0)
    return {
        "month": month,
        "income_k": income,
        "expense_k": expense,
        "balance_k": income + expense,
        "categories": [
            {"category": r["category"], "total_k": r["total_k"], "count": r["n"]}
            for r in rows
        ],
    }


def categories_with_totals(store: Store, month: str | None = None) -> list[dict]:
    sql = ("SELECT category, COUNT(*) n, SUM(amount_kopecks) total_k FROM transactions"
           " WHERE currency='RUB'")
    params: list[str] = []
    if month:
        sql += " AND substr(date,1,7)=?"
        params.append(month)
    sql += " GROUP BY category ORDER BY category"
    rows = store.conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def report_daily(store: Store, month: str) -> list[dict]:
    """Дневной ряд расходов за месяц (непродажные дни отсутствуют в выводе)."""
    rows = store.conn.execute(
        "SELECT date, SUM(amount_kopecks) AS total_k FROM transactions"
        " WHERE substr(date,1,7)=? AND currency='RUB' GROUP BY date ORDER BY date",
        (month,),
    ).fetchall()
    return [{"date": r["date"], "total_k": r["total_k"]} for r in rows]


BUDGET_EXCLUDED = {"income", "transfers"}  # не потребление: лимиты на них не ставим


def budgets_progress(store: Store, month: str, known: set[str] | None = None) -> list[dict]:
    """Прогресс по бюджетам категорий за месяц (знаковая сумма: возвраты уменьшают расход).

    `known` — имена категорий таксономии: бюджеты удалённых категорий (ручная правка TOML) не выводим.
    """
    budgets = store.budget_map()
    if not budgets:
        return []
    spent_rows = store.conn.execute(
        "SELECT category, SUM(amount_kopecks) AS s FROM transactions"
        " WHERE substr(date,1,7)=? AND currency='RUB' GROUP BY category",
        (month,),
    ).fetchall()
    spent = {r["category"]: -r["s"] for r in spent_rows}  # расход = минус знаковая сумма
    out: list[dict] = []
    for category, budget_k in sorted(budgets.items()):
        if category in BUDGET_EXCLUDED or (known is not None and category not in known):
            continue
        spent_k = spent.get(category, 0)
        spend_for_limits = max(0, spent_k)  # возвраты сверх трат не увеличивают остаток
        pct = (spend_for_limits / budget_k * 100) if budget_k else 0.0
        out.append({
            "category": category,
            "budget_k": budget_k,
            "spent_k": spent_k,
            "remaining_k": budget_k - spend_for_limits,
            "over_k": max(0, spend_for_limits - budget_k),
            "over": spend_for_limits > budget_k,
            "pct": pct,
        })
    return out


def confidence_calibration(store: Store, current_threshold: float = 0.9,
                           candidates: tuple[float, ...] = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9)) -> dict:
    """Калибровка порога авто-приёма по фактам: где LLM ошибался (человек исправил категорию).

    Берутся строки с предложением LLM (`category_llm`). «Решено» = review_status != 'pending';
    «совпало» = итоговая категория равна предложению LLM; «исправлено» = человек выбрал другую
    (в т.ч. автопринятые, позже поправленные: source='correction'). skipped — не сигнал качества.
    Для кандидатных порогов t считается: сколько бы авто-приняли и сколько из них ошибочных.
    """
    rows = store.conn.execute(
        "SELECT confidence, category, category_llm, review_status FROM transactions"
        " WHERE category_llm IS NOT NULL AND category_llm != ''").fetchall()

    resolved = [r for r in rows if r["review_status"] != "pending" and r["review_status"] != "skipped"]
    pending = sum(1 for r in rows if r["review_status"] == "pending")
    skipped = sum(1 for r in rows if r["review_status"] == "skipped")

    def _wrong(row) -> bool:
        return row["category"] != row["category_llm"]

    buckets: dict[str, dict] = {}
    for r in resolved:
        key = f"{int(r['confidence'] * 10) / 10:.1f}"
        b = buckets.setdefault(key, {"bucket": key, "n": 0, "agreed": 0, "corrected": 0})
        b["n"] += 1
        b["corrected" if _wrong(r) else "agreed"] += 1
    for b in buckets.values():
        b["wrong_rate"] = b["corrected"] / b["n"] if b["n"] else 0.0

    thresholds = []
    for t in candidates:
        accepted = [r for r in resolved if r["confidence"] >= t]
        wrong = sum(1 for r in accepted if _wrong(r))
        thresholds.append({
            "threshold": t,
            "accepted": len(accepted),
            "corrected": wrong,
            "coverage": len(accepted) / len(resolved) if resolved else 0.0,
            "wrong_rate": wrong / len(accepted) if accepted else 0.0,
        })

    return {
        "total": len(rows),
        "resolved": len(resolved),
        "pending": pending,
        "skipped": skipped,
        "low_data": len(resolved) < 20,
        "buckets": sorted(buckets.values(), key=lambda b: float(b["bucket"]), reverse=True),
        "thresholds": thresholds,
        "current_threshold": float(current_threshold),
    }