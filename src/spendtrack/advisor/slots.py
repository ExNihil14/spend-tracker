"""Deterministic slot parsing for the Phase C advisor (no LLM calls)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from spendtrack.advisor.facts import Period, parse_period
from spendtrack.taxonomy import Taxonomy

__all__ = ["Slots", "category_aliases", "parse_slot_payload", "parse_slots"]

METRICS = ("total", "category", "budget", "trend", "top", "unknown")

_BUDGET_WORDS = ("бюджет", "перерасход", "лимит")
_TREND_WORDS = ("тренд", "динамик", "средн", "по дням")
_TOP_WORDS = ("топ", "больше всего", "крупн")
_TOTAL_WORDS = ("сколько", "потрат", "расход", "итог", "всего")
_COMPARE_WORDS = ("сравн", "к прошл", "динамик", "тренд")
_PERIOD_HINT = ("последн", "месяц", "дн")


@dataclass(frozen=True)
class Slots:
    period: Period
    metric: str
    category: str | None
    top_n: int
    compare: bool
    ask_back: str | None


def _norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def category_aliases(taxonomy: Taxonomy) -> dict[str, set[str]]:
    """alias -> set(canonical names); the caller rejects collisions for matching."""
    out: dict[str, set[str]] = {}
    for c in taxonomy.categories:
        forms = {c.name.replace("-", " "), _norm(c.display_name)}
        for part in re.split(r",| и |/", _norm(c.display_name)):
            part = part.strip()
            if part:
                forms.add(part)
        for form in forms:
            if form:
                out.setdefault(form, set()).add(c.name)
    return out


def _match_category(text: str, taxonomy: Taxonomy) -> tuple[str | None, bool]:
    """(category, ambiguous) — longest alias first, word boundaries."""
    aliases = category_aliases(taxonomy)
    for form in sorted(aliases, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(form) + r"(?!\w)", text):
            names = aliases[form]
            if len(names) > 1:
                return None, True
            return next(iter(names)), False
    return None, False


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _default_period(today: date) -> Period:
    p = parse_period("этот месяц", today)
    assert p is not None
    return p


def _metric(t: str, category: str | None) -> str:
    if _has(t, _BUDGET_WORDS):
        return "budget"
    if _has(t, _TREND_WORDS):
        return "trend"
    if _has(t, _TOP_WORDS):
        return "top"
    if category is not None:
        return "category"
    if _has(t, _TOTAL_WORDS):
        return "total"
    return "unknown"


def _top_n(t: str) -> tuple[int, str | None]:
    m = re.search(r"топ[-\s]?(\d{1,2})", t)
    if not m:
        return 3, None
    n = int(m.group(1))
    if not 1 <= n <= 10:
        return 3, "top_n"
    return n, None


def parse_slots(text: str, today: date, taxonomy: Taxonomy) -> Slots:
    """Deterministic slot fill; returns ask_back instead of raising."""
    t = _norm(text)
    period = parse_period(t, today)
    if period is None:
        hinted = _has(t, _PERIOD_HINT) or re.search(r"\b\d{4}-\d{2}\b", t)
        if hinted:
            return Slots(_default_period(today), "unknown", None, 3, False, "period")
        period = _default_period(today)

    top_n, top_error = _top_n(t)
    if top_error:
        return Slots(period, "unknown", None, 3, False, top_error)

    category, ambiguous = _match_category(t, taxonomy)
    if ambiguous:
        return Slots(period, "unknown", None, top_n, False, "ambiguous_category")

    metric = _metric(t, category)
    compare = _has(t, _COMPARE_WORDS)
    ask_back = "unknown" if metric == "unknown" else None
    return Slots(period, metric, category, top_n, compare, ask_back)


def parse_slot_payload(payload: object, taxonomy: Taxonomy) -> dict | None:
    """Validate an LLM-produced slot payload (period is never accepted from the LLM)."""
    if not isinstance(payload, dict):
        return None
    if set(payload) - {"metric", "category", "top_n"}:
        return None
    metric = payload.get("metric")
    if metric not in METRICS or metric == "unknown":
        return None
    category = payload.get("category")
    if category is not None and (not isinstance(category, str)
                                 or not taxonomy.is_valid(category)):
        return None
    top_n = payload.get("top_n", 3)
    if not isinstance(top_n, int) or isinstance(top_n, bool) or not 1 <= top_n <= 10:
        return None
    return {"metric": metric, "category": category, "top_n": top_n}
