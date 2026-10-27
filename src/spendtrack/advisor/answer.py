"""Deterministic answer templates for the Phase C advisor (no LLM calls)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from spendtrack.advisor.slots import Slots
from spendtrack.store import fmt_amount
from spendtrack.taxonomy import Taxonomy, load_taxonomy

__all__ = ["Answer", "answer", "plural_ru"]

_ASK_BACK = {
    "period": "Уточни период: например, «в этом месяце» или «последние 30 дней».",
    "top_n": "Уточни N для топа: от 1 до 10.",
    "ambiguous_category": "Уточни категорию — подходит несколько.",
    "unknown": "Уточни период и категорию.",
}


@dataclass(frozen=True)
class Answer:
    text: str
    intent: str
    facts_used: tuple[str, ...]


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 100 in (11, 12, 13, 14):
        return many
    if n % 10 == 1:
        return one
    if n % 10 in (2, 3, 4):
        return few
    return many


def _money(kopecks: int) -> str:
    return f"{fmt_amount(int(kopecks))} ₽"


def _ops(n: int) -> str:
    return f"{n} {plural_ru(n, 'операция', 'операции', 'операций')}"


def _display(name: str, taxonomy: Taxonomy) -> str:
    return taxonomy.display(name) if taxonomy.is_valid(name) else name


def _compare_line(facts: dict, total: int) -> str:
    cmp_ = facts.get("compare")
    if not cmp_:
        return ""
    prev = int(cmp_.get("total") or 0)
    if prev <= 0:
        return " К прошлому периоду: нет данных."
    pct = (total - prev) * 100.0 / prev
    return f" К прошлому периоду: {pct:+.1f}%."


def _total(facts: dict, slots: Slots) -> Answer:
    text = f"За {facts['period']['label']} — {_money(facts['total'])} ({_ops(facts['tx_count'])})."
    if slots.compare:
        text += _compare_line(facts, facts["total"])
    return Answer(text, "total", ("total", "tx_count", "period"))


def _category(facts: dict, slots: Slots, taxonomy: Taxonomy) -> Answer:
    name = slots.category or ""
    cats = {c["name"]: c for c in facts.get("categories") or []}
    c = cats.get(name)
    label = _display(name, taxonomy)
    if not c:
        return Answer(f"{label}: 0.00 ₽ (0 операций).", "category",
                      ("categories",))
    total = int(facts["total"])
    share = "—" if total <= 0 else f"{c['share_bp'] / 100:.1f}%"
    text = f"{label}: {_money(c['sum'])} ({share}, {_ops(c['count'])})."
    return Answer(text, "category", ("categories", "total"))


def _budget(facts: dict, taxonomy: Taxonomy) -> Answer:
    budgets = facts.get("budgets") or []
    over = [b for b in budgets if int(b["overrun"]) > 0]
    if not over:
        return Answer("В рамках бюджетов.", "budget", ("budgets",))
    parts = []
    for b in over:
        limit = int(b["limit"])
        pct = (int(b["spent"]) * 100.0 / limit) if limit > 0 else 0.0
        parts.append(f"{_display(b['category'], taxonomy)} — {_money(b['spent'])} из "
                     f"{_money(limit)} (+{_money(b['overrun'])}), {pct:.0f}% лимита")
    return Answer("Перерасход: " + "; ".join(parts) + ".", "budget", ("budgets",))


def _trend(facts: dict, slots: Slots, today: date | None) -> Answer:
    daily = facts.get("daily") or []
    if not daily:
        return Answer("Нет трат за период.", "trend", ("daily",))
    period = facts["period"]
    if today is not None and period.get("month") == f"{today.year:04d}-{today.month:02d}":
        days = today.day
    else:
        start = date.fromisoformat(period["start"])
        end = date.fromisoformat(period["end"])
        days = (end - start).days + 1
    avg = facts["total"] // max(1, days)
    peak = max(daily, key=lambda d: int(d["sum"]))
    text = (f"Средний день {_money(avg)}; максимум {peak['date']} — "
            f"{_money(peak['sum'])}.")
    if slots.compare:
        text += _compare_line(facts, facts["total"])
    return Answer(text, "trend", ("daily", "total", "period"))


def _top(facts: dict, slots: Slots, taxonomy: Taxonomy) -> Answer:
    cats = list(facts.get("categories") or [])
    if not cats:
        return Answer("Нет трат за период.", "top", ("categories",))
    cats.sort(key=lambda c: (-int(c["sum"]), c["name"]))
    n = max(1, min(int(slots.top_n), len(cats)))
    parts = [f"{_display(c['name'], taxonomy)} — {_money(c['sum'])} "
             f"({c['share_bp'] / 100:.1f}%)" for c in cats[:n]]
    return Answer(f"Топ-{n}: " + ", ".join(parts) + ".", "top", ("categories",))


def answer(facts: dict, slots: Slots, taxonomy: Taxonomy | None = None,
           today: date | None = None) -> Answer:
    """Render a deterministic answer for known intents; ask back otherwise."""
    tx = taxonomy or load_taxonomy()
    if slots.ask_back or slots.metric == "unknown":
        reason = slots.ask_back or "unknown"
        return Answer(_ASK_BACK.get(reason, _ASK_BACK["unknown"]), "ask_back", ())
    if slots.metric == "total":
        return _total(facts, slots)
    if slots.metric == "category":
        return _category(facts, slots, tx)
    if slots.metric == "budget":
        return _budget(facts, tx)
    if slots.metric == "trend":
        return _trend(facts, slots, today)
    if slots.metric == "top":
        return _top(facts, slots, tx)
    return Answer(_ASK_BACK["unknown"], "ask_back", ())
