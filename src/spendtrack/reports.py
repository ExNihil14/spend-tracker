from __future__ import annotations

from spendtrack.store import Store


def report_month(store: Store, month: str) -> dict:
    rows = store.conn.execute(
        "SELECT category, SUM(amount_kopecks) AS total_k, COUNT(*) AS n"
        " FROM transactions WHERE substr(date,1,7)=? GROUP BY category ORDER BY total_k",
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
    sql = ("SELECT category, COUNT(*) n, SUM(amount_kopecks) total_k FROM transactions")
    params: list[str] = []
    if month:
        sql += " WHERE substr(date,1,7)=?"
        params.append(month)
    sql += " GROUP BY category ORDER BY category"
    rows = store.conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]