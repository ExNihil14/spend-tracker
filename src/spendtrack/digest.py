"""Дайджест недели + флаги аномалий — read-only, вычисление на лету (состояние не хранится).

Окно — скользящее: [сегодня - days + 1 .. сегодня] (по умолчанию 7 дней), сравнение с предыдущим
окном той же длины. Переводы (`transfers`) исключены везде; доходы участвуют только в итогах
(расход/доход/баланс), топы и аномалии считаются по расходам.

Аномалии (не больше MAX_ANOMALIES, сортировка по score — шкалы разные: для `large_expense`/`price_jump`
это отношение к базе, для near-дублей — число копий; порядок условный, детерминированный):
* `large_expense` — |сумма| >= ANOMALY_FACTOR × медианы |расходов| категории за 90 дней,
  в категории >= MIN_CATEGORY_OBSERVATIONS наблюдений (включая саму транзакцию) и сумма не меньше
  порога-пола ANOMALY_MIN_AMOUNT_K (мелочь не флагаем даже при большом отклонении);
* `price_jump` — первое списание после активного рекурринга, отклоняющееся от его цены на >= PRICE_JUMP_RATIO,
  и дата этого первого отклонения внутри окна (событие смены цены; повторные списания по новой цене не флагуются);
* `near_duplicate` — >= 2 расходов в один день у одного мерчанта с одинаковой |суммой|
  (fingerprint их не склеил: различаются описание/строка выписки).

Ничего не записывается, авто-действий нет; в тестах `today` инжектируется.
"""
from __future__ import annotations

import statistics
from datetime import UTC, date, datetime, timedelta

from spendtrack.recurring import detect_recurring
from spendtrack.store import Store, fmt_amount_signed

DEFAULT_DAYS = 7
TOP_CATEGORIES = 5
MAX_ANOMALIES = 10
MEDIAN_WINDOW_DAYS = 90
ANOMALY_FACTOR = 3.0
MIN_CATEGORY_OBSERVATIONS = 10
ANOMALY_MIN_AMOUNT_K = 100_000  # 1000 ₽: пол для «крупной суммы»
PRICE_JUMP_RATIO = 0.10
UPCOMING_DAYS = 14
MAX_UPCOMING = 5
EXCLUDED_CATEGORIES = ("transfers",)

ANOMALY_LABELS = {
    "large_expense": "крупная сумма",
    "price_jump": "скачок цены",
    "near_duplicate": "near-дубль",
}

_EXCLUDED = ",".join("?" * len(EXCLUDED_CATEGORIES))
_EXCLUDED_PARAMS: tuple[str, ...] = EXCLUDED_CATEGORIES


def _totals(store: Store, start: str, end: str) -> dict:
    row = store.conn.execute(
        "SELECT"
        " COALESCE(SUM(CASE WHEN amount_kopecks > 0 THEN amount_kopecks END), 0) AS income_k,"
        " COALESCE(SUM(CASE WHEN amount_kopecks < 0 THEN amount_kopecks END), 0) AS expense_k,"
        " COUNT(*) AS n"
        " FROM transactions WHERE date >= ? AND date <= ?"
        f" AND category NOT IN ({_EXCLUDED})",
        (start, end, *_EXCLUDED_PARAMS),
    ).fetchone()
    return {
        "income_k": row["income_k"],
        "expense_k": row["expense_k"],
        "balance_k": row["income_k"] + row["expense_k"],
        "count": row["n"],
    }


def _top_categories(store: Store, start: str, end: str,
                    prev_start: str, prev_end: str) -> list[dict]:
    rows = store.conn.execute(
        "SELECT category, SUM(amount_kopecks) AS total_k, COUNT(*) AS n"
        " FROM transactions WHERE date >= ? AND date <= ? AND amount_kopecks < 0"
        f" AND category NOT IN ({_EXCLUDED})"
        " GROUP BY category ORDER BY total_k ASC LIMIT ?",
        (start, end, *_EXCLUDED_PARAMS, TOP_CATEGORIES),
    ).fetchall()
    prev = {
        r["category"]: r["total_k"]
        for r in store.conn.execute(
            "SELECT category, SUM(amount_kopecks) AS total_k FROM transactions"
            " WHERE date >= ? AND date <= ? AND amount_kopecks < 0"
            f" AND category NOT IN ({_EXCLUDED}) GROUP BY category",
            (prev_start, prev_end, *_EXCLUDED_PARAMS),
        ).fetchall()
    }
    return [
        {
            "category": r["category"],
            "total_k": r["total_k"],
            "count": r["n"],
            "prev_k": prev.get(r["category"], 0),
            "delta_k": r["total_k"] - prev.get(r["category"], 0),
        }
        for r in rows
    ]


def _top_day(store: Store, start: str, end: str) -> dict | None:
    row = store.conn.execute(
        "SELECT date, SUM(amount_kopecks) AS total_k FROM transactions"
        " WHERE date >= ? AND date <= ? AND amount_kopecks < 0"
        f" AND category NOT IN ({_EXCLUDED})"
        " GROUP BY date ORDER BY total_k ASC LIMIT 1",
        (start, end, *_EXCLUDED_PARAMS),
    ).fetchone()
    return {"date": row["date"], "total_k": row["total_k"]} if row else None


def _large_expenses(store: Store, start: str, end: str, median_start: str) -> list[dict]:
    stats_rows = store.conn.execute(
        "SELECT category, amount_kopecks FROM transactions"
        " WHERE date >= ? AND date <= ? AND amount_kopecks < 0"
        f" AND category NOT IN ({_EXCLUDED})",
        (median_start, end, *_EXCLUDED_PARAMS),
    ).fetchall()
    by_category: dict[str, list[int]] = {}
    for r in stats_rows:
        by_category.setdefault(r["category"], []).append(abs(r["amount_kopecks"]))

    candidates = store.conn.execute(
        "SELECT date, description, merchant, category, amount_kopecks FROM transactions"
        " WHERE date >= ? AND date <= ? AND amount_kopecks < 0"
        f" AND category NOT IN ({_EXCLUDED})"
        " ORDER BY amount_kopecks ASC, id ASC",
        (start, end, *_EXCLUDED_PARAMS),
    ).fetchall()

    out: list[dict] = []
    for r in candidates:
        amounts = by_category.get(r["category"], [])
        if len(amounts) < MIN_CATEGORY_OBSERVATIONS:
            continue
        amount = abs(r["amount_kopecks"])
        median = statistics.median(amounts)
        if median <= 0 or amount < ANOMALY_MIN_AMOUNT_K or amount < ANOMALY_FACTOR * median:
            continue
        out.append({
            "type": "large_expense",
            "label": ANOMALY_LABELS["large_expense"],
            "date": r["date"],
            "merchant": r["merchant"] or r["description"],
            "category": r["category"],
            "amount_k": r["amount_kopecks"],
            "score": round(amount / median, 2),
            "median_k": int(median),
            "count": None,
            "prev_price_k": None,
        })
    return out


def _price_jumps(store: Store, subscriptions: list[dict], start: str, end: str) -> list[dict]:
    out: list[dict] = []
    for sub in subscriptions:
        if not sub["active"] or sub["price_k"] <= 0:
            continue
        rows = store.conn.execute(
            "SELECT date, amount_kopecks FROM transactions"
            " WHERE merchant = ? AND amount_kopecks < 0 AND date > ? AND date <= ?"
            " ORDER BY date ASC, id ASC",
            (sub["merchant"], sub["last_date"], end),
        ).fetchall()
        row = next(
            (r for r in rows if abs(abs(r["amount_kopecks"]) / sub["price_k"] - 1) >= PRICE_JUMP_RATIO),
            None,
        )
        if row is None or not start <= row["date"] <= end:
            continue
        amount = abs(row["amount_kopecks"])
        ratio = amount / sub["price_k"]
        out.append({
            "type": "price_jump",
            "label": ANOMALY_LABELS["price_jump"],
            "date": row["date"],
            "merchant": sub["merchant"],
            "category": sub["category"],
            "amount_k": row["amount_kopecks"],
            "score": round(ratio, 2),
            "median_k": None,
            "count": None,
            "prev_price_k": sub["price_k"],
        })
    return out


def _near_duplicates(store: Store, start: str, end: str) -> list[dict]:
    rows = store.conn.execute(
        "SELECT date, merchant, amount_kopecks, COUNT(*) AS n"
        " FROM transactions"
        " WHERE date >= ? AND date <= ? AND amount_kopecks < 0"
        "   AND merchant IS NOT NULL AND merchant != ''"
        f"   AND category NOT IN ({_EXCLUDED})"
        " GROUP BY date, merchant, amount_kopecks"
        " HAVING COUNT(*) >= 2",
        (start, end, *_EXCLUDED_PARAMS),
    ).fetchall()
    return [
        {
            "type": "near_duplicate",
            "label": ANOMALY_LABELS["near_duplicate"],
            "date": r["date"],
            "merchant": r["merchant"],
            "category": None,
            "amount_k": r["amount_kopecks"],
            "score": float(r["n"]),
            "median_k": None,
            "count": r["n"],
            "prev_price_k": None,
        }
        for r in rows
    ]


def _anomaly_detail(a: dict) -> str:
    """Текст детали для UI/CLI — суммы в отображаемой форме со знаком (fmt_amount_signed).

    `median_k`/`prev_price_k` хранятся магнитудами (медианы |сумм|, см. `_large_expenses`,
    `_price_jumps`), поэтому знак расхода для них ставим явно.
    """
    if a["type"] == "large_expense":
        return (f"{fmt_amount_signed(a['amount_k'])} ₽ — медиана категории"
                f" {fmt_amount_signed(-a['median_k'])} ₽ (×{a['score']:.1f})")
    if a["type"] == "price_jump":
        pct = (a["score"] - 1) * 100
        return (f"цена {fmt_amount_signed(a['amount_k'])} ₽ вместо"
                f" {fmt_amount_signed(-a['prev_price_k'])} ₽ ({pct:+.0f}%)")
    return f"{a['count']} списания по {fmt_amount_signed(a['amount_k'])} ₽ в один день"


def _upcoming(subscriptions: list[dict], ref: date) -> list[dict]:
    deadline = (ref + timedelta(days=UPCOMING_DAYS)).isoformat()
    items = [
        {
            "merchant": s["merchant"],
            "price_k": s["price_k"],
            "next_expected": s["next_expected"],
            "days_until": (date.fromisoformat(s["next_expected"]) - ref).days,
        }
        for s in subscriptions
        if s["active"] and s["next_expected"] <= deadline
    ]
    items.sort(key=lambda u: (u["next_expected"], u["merchant"]))
    return items[:MAX_UPCOMING]


def build_digest(store: Store, days: int = DEFAULT_DAYS, today: date | None = None) -> dict:
    """Сводка за скользящее окно + аномалии; ничего не пишет в БД."""
    days = max(1, int(days))
    ref = today or datetime.now(UTC).date()
    start = ref - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    median_start = ref - timedelta(days=MEDIAN_WINDOW_DAYS - 1)
    start_s, end_s = start.isoformat(), ref.isoformat()
    prev_start_s, prev_end_s = prev_start.isoformat(), prev_end.isoformat()

    totals = _totals(store, start_s, end_s)
    prev = _totals(store, prev_start_s, prev_end_s)
    subscriptions = detect_recurring(store, ref)

    anomalies = (
        _large_expenses(store, start_s, end_s, median_start.isoformat())
        + _price_jumps(store, subscriptions, start_s, end_s)
        + _near_duplicates(store, start_s, end_s)
    )
    anomalies.sort(key=lambda a: (-a["score"], a["date"], a["type"]))
    anomalies = anomalies[:MAX_ANOMALIES]
    for a in anomalies:
        a["detail"] = _anomaly_detail(a)

    return {
        "period": {"from": start_s, "to": end_s, "days": days},
        "prev_period": {"from": prev_start_s, "to": prev_end_s},
        "income_k": totals["income_k"],
        "expense_k": totals["expense_k"],
        "balance_k": totals["balance_k"],
        "expense_delta_k": totals["expense_k"] - prev["expense_k"],
        "prev": {
            "income_k": prev["income_k"],
            "expense_k": prev["expense_k"],
            "balance_k": prev["balance_k"],
        },
        "avg_per_day_k": round(totals["expense_k"] / days),
        "transaction_count": totals["count"],
        "top_categories": _top_categories(store, start_s, end_s, prev_start_s, prev_end_s),
        "top_day": _top_day(store, start_s, end_s),
        "pending_count": store.pending_count(),
        "upcoming": _upcoming(subscriptions, ref),
        "anomalies": anomalies,
    }
