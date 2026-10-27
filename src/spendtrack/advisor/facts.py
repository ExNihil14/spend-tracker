"""Phase C advisor: deterministic fact-sheet (no LLM, aggregates only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from spendtrack.config import base_currency
from spendtrack.reports import budgets_progress, report_daily, report_month
from spendtrack.store import Store, month_bounds
from spendtrack.taxonomy import Taxonomy, load_taxonomy

__all__ = ["Period", "build_facts", "parse_period", "validate_facts"]

_MONTH_FORMS = {
    "январь": 1, "января": 1, "январе": 1,
    "февраль": 2, "февраля": 2, "феврале": 2,
    "март": 3, "марта": 3, "марте": 3,
    "апрель": 4, "апреля": 4, "апреле": 4,
    "май": 5, "мая": 5, "мае": 5,
    "июнь": 6, "июня": 6, "июне": 6,
    "июль": 7, "июля": 7, "июле": 7,
    "август": 8, "августа": 8, "августе": 8,
    "сентябрь": 9, "сентября": 9, "сентябре": 9,
    "октябрь": 10, "октября": 10, "октябре": 10,
    "ноябрь": 11, "ноября": 11, "ноябре": 11,
    "декабрь": 12, "декабря": 12, "декабре": 12,
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class Period:
    start: str          # inclusive, YYYY-MM-DD
    end: str            # inclusive, YYYY-MM-DD
    label: str
    month: str | None   # YYYY-MM for calendar months


def _month_period(month: str) -> Period:
    start, end_excl = month_bounds(month)
    end = (date.fromisoformat(end_excl) - timedelta(days=1)).isoformat()
    return Period(start=start, end=end, label=month, month=month)


def parse_period(text: str, today: date) -> Period | None:
    """Deterministic period parser (C1 subset: periods used by templates)."""
    t = (text or "").lower().replace("ё", "е")
    m = re.search(r"\b(\d{4})-(\d{2})\b", t)
    if m:
        try:
            date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
        return _month_period(f"{m.group(1)}-{m.group(2)}")
    m = re.search(r"(?:последн\w*|за последние)\s+(\d+)\s+(?:дн\w*|день)", t)
    if m:
        n = int(m.group(1))
        if not 1 <= n <= 365:
            return None
        start = today - timedelta(days=n - 1)
        return Period(start.isoformat(), today.isoformat(), f"последние {n} дней", None)
    if "месяц" in t and "прошл" in t:
        year, month = (today.year, today.month - 1) if today.month > 1 \
            else (today.year - 1, 12)
        return _month_period(f"{year:04d}-{month:02d}")
    if "месяц" in t and ("этот" in t or "этом" in t or "текущ" in t):
        return _month_period(f"{today.year:04d}-{today.month:02d}")
    for form, num in _MONTH_FORMS.items():
        if re.search(rf"\b{form}\b", t):
            year = today.year if num <= today.month else today.year - 1
            return _month_period(f"{year:04d}-{num:02d}")
    return None


def _share_bp(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return (part * 10_000 + whole // 2) // whole


def _spend_daily(store: Store, month: str) -> list[dict]:
    return [{"date": row["date"], "sum": -int(row["total_k"])}
            for row in report_daily(store, month) if int(row["total_k"]) < 0]


def _foreign(store: Store, start: str, end: str) -> dict:
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    base = base_currency()
    rows = store.conn.execute(
        "SELECT DISTINCT COALESCE(UPPER(NULLIF(currency, '')), 'RUB') AS cur"
        " FROM transactions WHERE date >= ? AND date < ?"
        " AND COALESCE(UPPER(NULLIF(currency, '')), 'RUB') != ?",
        (start, end_excl, base),
    ).fetchall()
    codes = sorted({r["cur"] for r in rows if r["cur"] and r["cur"] != base})
    return {"count": _foreign_count(store, start, end_excl, base), "currencies": codes}


def _foreign_count(store: Store, start: str, end_excl: str, base: str) -> int:
    row = store.conn.execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE date >= ? AND date < ?"
        " AND COALESCE(UPPER(NULLIF(currency, '')), 'RUB') != ?",
        (start, end_excl, base),
    ).fetchone()
    return int(row["c"])


def _count_rub(store: Store, start: str, end: str) -> int:
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    row = store.conn.execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE date >= ? AND date < ?"
        " AND COALESCE(UPPER(NULLIF(currency, '')), 'RUB') = ?",
        (start, end_excl, base_currency()),
    ).fetchone()
    return int(row["c"])


def _prev_month(month: str) -> str:
    year, num = int(month[:4]), int(month[5:7])
    year, num = (year - 1, 12) if num == 1 else (year, num - 1)
    return f"{year:04d}-{num:02d}"


def _month_facts(store: Store, period: Period, taxonomy: Taxonomy,
                 today: date | None = None) -> dict:
    month = period.month or ""
    rep = report_month(store, month)
    total = -int(rep["expense_k"])
    tx_count = sum(int(c["count"]) for c in rep["categories"])
    cats = []
    for c in rep["categories"]:
        k = int(c["total_k"])
        if k >= 0:
            continue
        cats.append({"name": c["category"], "sum": -k, "count": int(c["count"]),
                     "share_bp": _share_bp(-k, total)})
    cats.sort(key=lambda c: (-c["sum"], c["name"]))
    budgets = [{"category": b["category"], "limit": int(b["budget_k"]),
                "spent": int(b["spent_k"]), "overrun": int(b["over_k"])}
               for b in budgets_progress(store, month,
                                         known={c.name for c in taxonomy.categories})]
    prev = _prev_month(month)
    prev_rep = report_month(store, prev)
    prev_daily = _spend_daily(store, prev)
    compare_label = prev
    if today is not None and month == f"{today.year:04d}-{today.month:02d}":
        cutoff = f"{prev}-{today.day:02d}"
        prev_daily = [d for d in prev_daily if d["date"] <= cutoff]
        compare_label = f"{prev} по {today.day:02d}"
    return {
        "period": {"start": period.start, "end": period.end, "label": period.label,
                   "month": period.month},
        "base_currency": base_currency(),
        "total": total,
        "tx_count": tx_count,
        "categories": cats,
        "budgets": budgets,
        "daily": _spend_daily(store, month),
        "excluded_foreign": _foreign(store, period.start, period.end),
        "compare": {"total": -int(prev_rep["expense_k"]) if compare_label == prev
                    else sum(d["sum"] for d in prev_daily),
                    "daily": prev_daily, "label": compare_label},
        "unavailable": [],
    }


def _months_between(start: date, end: date) -> list[str]:
    out = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _range_daily(store: Store, start: str, end: str) -> list[dict]:
    acc: dict[str, int] = {}
    for month in _months_between(date.fromisoformat(start), date.fromisoformat(end)):
        for row in report_daily(store, month):
            if start <= row["date"] <= end and int(row["total_k"]) < 0:
                acc[row["date"]] = acc.get(row["date"], 0) - int(row["total_k"])
    return [{"date": d, "sum": acc[d]} for d in sorted(acc)]


def _range_facts(store: Store, period: Period, taxonomy: Taxonomy) -> dict:
    del taxonomy  # categories/budgets are unavailable for non-month periods
    start_d, end_d = date.fromisoformat(period.start), date.fromisoformat(period.end)
    length = (end_d - start_d).days + 1
    prev_end = start_d - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    daily = _range_daily(store, period.start, period.end)
    prev_daily = _range_daily(store, prev_start.isoformat(), prev_end.isoformat())
    return {
        "period": {"start": period.start, "end": period.end, "label": period.label,
                   "month": None},
        "base_currency": base_currency(),
        "total": sum(d["sum"] for d in daily),
        "tx_count": _count_rub(store, period.start, period.end),
        "categories": None,
        "budgets": None,
        "daily": daily,
        "excluded_foreign": _foreign(store, period.start, period.end),
        "compare": {"total": sum(d["sum"] for d in prev_daily),
                    "daily": prev_daily,
                    "label": f"{prev_start.isoformat()}..{prev_end.isoformat()}"},
        "unavailable": ["categories", "budgets"],
    }


def build_facts(store: Store, period: Period, taxonomy: Taxonomy | None = None,
                today: date | None = None) -> dict:
    """Build and validate the aggregate-only fact-sheet for a period."""
    tx = taxonomy or load_taxonomy()
    facts = (_month_facts(store, period, tx, today) if period.month
             else _range_facts(store, period, tx))
    validate_facts(facts, taxonomy=tx)
    return facts


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def validate_facts(facts: dict, taxonomy: Taxonomy | None = None) -> None:
    """Structural allow-list: exact keys, types, ISO dates, taxonomy category names."""
    tx = taxonomy or load_taxonomy()
    names = {c.name for c in tx.categories}
    top = {"period", "base_currency", "total", "tx_count", "categories", "budgets",
           "daily", "excluded_foreign", "compare", "unavailable"}
    _expect(isinstance(facts, dict) and set(facts) == top, "facts: неверный набор ключей")
    p = facts["period"]
    _expect(isinstance(p, dict) and set(p) == {"start", "end", "label", "month"},
            "period: неверный набор ключей")
    _expect(isinstance(p["start"], str) and _DATE_RE.fullmatch(p["start"]) is not None,
            "period.start: ожидается YYYY-MM-DD")
    _expect(isinstance(p["end"], str) and _DATE_RE.fullmatch(p["end"]) is not None,
            "period.end: ожидается YYYY-MM-DD")
    _expect(isinstance(p["label"], str) and p["label"], "period.label: пусто")
    _expect(p["month"] is None or (isinstance(p["month"], str)
                                   and _MONTH_RE.fullmatch(p["month"]) is not None),
            "period.month: ожидается YYYY-MM или null")
    _expect(facts["base_currency"] == base_currency(), "base_currency: неверно")
    _expect(isinstance(facts["total"], int) and facts["total"] >= 0, "total: int >= 0")
    _expect(isinstance(facts["tx_count"], int) and facts["tx_count"] >= 0,
            "tx_count: int >= 0")
    cats = facts["categories"]
    if cats is not None:
        _expect(isinstance(cats, list), "categories: список или null")
        for c in cats:
            _expect(isinstance(c, dict) and set(c) == {"name", "sum", "count", "share_bp"},
                    "categories[]: неверный набор ключей")
            _expect(isinstance(c["name"], str) and c["name"] in names,
                    "categories[].name: не из таксономии")
            _expect(isinstance(c["sum"], int) and isinstance(c["count"], int)
                    and isinstance(c["share_bp"], int), "categories[]: ожидаются int")
    budgets = facts["budgets"]
    if budgets is not None:
        _expect(isinstance(budgets, list), "budgets: список или null")
        for b in budgets:
            _expect(isinstance(b, dict)
                    and set(b) == {"category", "limit", "spent", "overrun"},
                    "budgets[]: неверный набор ключей")
            _expect(isinstance(b["category"], str) and b["category"] in names,
                    "budgets[].category: не из таксономии")
            _expect(all(isinstance(b[k], int) for k in ("limit", "spent", "overrun")),
                    "budgets[]: ожидаются int")
    daily = facts["daily"]
    _expect(isinstance(daily, list), "daily: список")
    for d in daily:
        _expect(isinstance(d, dict) and set(d) == {"date", "sum"}, "daily[]: неверный набор ключей")
        _expect(isinstance(d["date"], str) and _DATE_RE.fullmatch(d["date"]) is not None,
                "daily[].date: ожидается YYYY-MM-DD")
        _expect(isinstance(d["sum"], int), "daily[].sum: ожидается int")
    ex = facts["excluded_foreign"]
    _expect(isinstance(ex, dict) and set(ex) == {"count", "currencies"},
            "excluded_foreign: неверный набор ключей")
    _expect(isinstance(ex["count"], int) and isinstance(ex["currencies"], list)
            and all(isinstance(c, str) for c in ex["currencies"]),
            "excluded_foreign: неверные типы")
    cmp_ = facts["compare"]
    if cmp_ is not None:
        _expect(isinstance(cmp_, dict) and set(cmp_) == {"total", "daily", "label"},
                "compare: неверный набор ключей")
        _expect(isinstance(cmp_["total"], int) and isinstance(cmp_["label"], str),
                "compare: неверные типы")
        _expect(isinstance(cmp_["daily"], list), "compare.daily: список")
    _expect(isinstance(facts["unavailable"], list)
            and set(facts["unavailable"]) <= {"categories", "budgets"},
            "unavailable: список из categories/budgets")
