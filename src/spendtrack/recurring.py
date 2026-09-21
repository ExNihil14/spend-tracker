"""Детекция рекуррингов/подписок — read-only эвристика, без хранения состояния.

Критерий находки: у мерчанта ≥3 списаний, суммы которых лежат в ±5% от медианы
кластера, промежутки между списаниями — 27–34 дня (медиана 28–31), допускается
один пропуск месяца (разрыв 56–62 дня). Переводы и положительные суммы не участвуют.

«Цена» = медиана кластера (по всем списаниям; устойчива к разовым скачкам), категория = самая
частая у списаний. Интервалы и число повторов считаются по уникальным дням (дубль в один день —
одно списание). active — последнее списание не старше ACTIVE_DAYS от опорной даты
(сегодня; в тестах инжектируется).
"""
from __future__ import annotations

import sqlite3
import statistics
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

from spendtrack.store import Store

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.05
GAP_MIN, GAP_MAX = 27, 34
SKIP_GAP_MIN, SKIP_GAP_MAX = 56, 62
MEDIAN_GAP_MIN, MEDIAN_GAP_MAX = 28, 31
MAX_SKIPS = 1
ACTIVE_DAYS = 40
EXCLUDED_CATEGORIES = ("transfers",)


def _parse_iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _cluster_median(cluster: list[sqlite3.Row]) -> float:
    """Медиана кластера за O(1): строки добавляются в порядке возрастания суммы.

    Инвариант «кластер отсортирован по amount_kopecks» обеспечивает `_amount_clusters`
    (обход rows идёт по возрастанию, append в конец). Guard ниже ловит нарушение инварианта
    при будущем рефакторинге (стоит O(1), не O(k)).
    """
    n = len(cluster)
    assert n == 1 or cluster[-1]["amount_kopecks"] >= cluster[-2]["amount_kopecks"], (
        "нарушен инвариант сортировки кластера — пересмотреть _cluster_median")
    mid = n // 2
    if n % 2:
        return float(cluster[mid]["amount_kopecks"])
    return (cluster[mid - 1]["amount_kopecks"] + cluster[mid]["amount_kopecks"]) / 2


def _amount_clusters(rows: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    """Жадная кластеризация сумм мерчанта: ±AMOUNT_TOLERANCE от бегущей медианы."""
    clusters: list[list[sqlite3.Row]] = []
    for row in sorted(rows, key=lambda r: r["amount_kopecks"]):
        amount = row["amount_kopecks"]
        for cluster in clusters:
            median = _cluster_median(cluster)
            if abs(amount - median) <= abs(median) * AMOUNT_TOLERANCE:
                cluster.append(row)
                break
        else:
            clusters.append([row])
    return clusters


def _check_gaps(gaps: list[int]) -> tuple[bool, int, int]:
    """(подходит, медианный интервал, число пропусков месяца)."""
    normal = [g for g in gaps if GAP_MIN <= g <= GAP_MAX]
    skips = sum(1 for g in gaps if SKIP_GAP_MIN <= g <= SKIP_GAP_MAX)
    if not normal or len(normal) + skips != len(gaps) or skips > MAX_SKIPS:
        return False, 0, 0
    median_gap = int(statistics.median(normal))
    if not MEDIAN_GAP_MIN <= median_gap <= MEDIAN_GAP_MAX:
        return False, 0, 0
    return True, median_gap, skips


def detect_recurring(store: Store, today: date | None = None) -> list[dict]:
    """Список найденных рекуррингов: активные сверху, затем по убыванию цены."""
    ref = today or datetime.now(UTC).date()
    marks = ",".join("?" * len(EXCLUDED_CATEGORIES))
    rows = store.conn.execute(
        "SELECT merchant, amount_kopecks, date, category FROM transactions"
        " WHERE amount_kopecks < 0 AND currency='RUB' AND merchant IS NOT NULL AND merchant != ''"
        " AND date IS NOT NULL AND date != ''"
        f" AND category NOT IN ({marks})"
        " ORDER BY merchant, date, id",
        EXCLUDED_CATEGORIES,
    ).fetchall()

    by_merchant: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_merchant.setdefault(row["merchant"], []).append(row)

    items: list[dict] = []
    for merchant, transactions in by_merchant.items():
        if len(transactions) < MIN_OCCURRENCES:
            continue
        for cluster in _amount_clusters(transactions):
            valid = [row for row in cluster if _parse_iso(row["date"]) is not None]
            if len(valid) < MIN_OCCURRENCES:
                continue
            by_day = {_parse_iso(row["date"]): row for row in valid}
            days = sorted(by_day)
            if len(days) < MIN_OCCURRENCES:
                continue
            gaps = [(b - a).days for a, b in pairwise(days)]
            ok, median_gap, skips = _check_gaps(gaps)
            if not ok:
                continue
            # Цена/категория — по всем списаниям кластера (спека: «медиана кластера»),
            # дни уникальны только для интервалов и счётчика повторов.
            amounts = [row["amount_kopecks"] for row in valid]
            category = Counter(row["category"] for row in valid).most_common(1)[0][0]
            first, last = days[0], days[-1]
            days_since = (ref - last).days
            items.append({
                "merchant": merchant,
                "category": category,
                "price_k": -int(statistics.median(amounts)),
                "occurrences": len(days),
                "first_date": first.isoformat(),
                "last_date": last.isoformat(),
                "median_gap_days": median_gap,
                "skipped_months": skips,
                "days_since_last": days_since,
                "active": days_since <= ACTIVE_DAYS,
                "next_expected": (last + timedelta(days=median_gap)).isoformat(),
            })
    items.sort(key=lambda i: (not i["active"], -i["price_k"], i["merchant"]))
    return items


def recurring_summary(store: Store, today: date | None = None,
                      subscriptions: list[dict] | None = None) -> dict:
    """Список + агрегаты: активные считаются в месячный итог, stale — нет.

    `subscriptions` — уже найденные рекурринги (дашборд считает `detect_recurring` один раз
    на страницу; иначе тяжёлый проход по истории выполняется дважды).
    Ключ `subscriptions` (не `items`): в Jinja `dict.items` — метод, а не ключ.
    """
    items = subscriptions if subscriptions is not None else detect_recurring(store, today)
    active = [s for s in items if s["active"]]
    return {
        "subscriptions": items,
        "active_count": len(active),
        "stale_count": len(items) - len(active),
        "monthly_total_k": sum(s["price_k"] for s in active),
    }
