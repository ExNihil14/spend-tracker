"""Consumers (CLI/PWA) call this facade; advisor internals stay behind it.

This module is the only place that may import facts/slots/llm directly. The public Phase C
contract remains `spendtrack.advisor.contract`; `_answer_question` is intentionally private.
"""
from __future__ import annotations

import re
from datetime import date

from spendtrack.advisor.answer import Answer
from spendtrack.advisor.contract import TemplateAdvisor, run_advisor_flow
from spendtrack.advisor.facts import build_facts, parse_period
from spendtrack.advisor.slots import _parse_slots
from spendtrack.store import Store
from spendtrack.taxonomy import Taxonomy


def _answer_question(
    question: str,
    store: Store,
    taxonomy: Taxonomy,
    today: date,
    month: str | None = None,
) -> tuple[Answer, dict]:
    """Build facts/slots and run the frozen advisor flow; month errors → ValueError."""
    period = None
    if month is not None:
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError("--month ожидается YYYY-MM")
        period = parse_period(month, today)
        if period is None:
            raise ValueError("некорректный --month")
    slots = _parse_slots(question, today, taxonomy, period_override=period)
    facts = build_facts(store, slots.period, taxonomy, today)
    result = run_advisor_flow(
        TemplateAdvisor(), question, facts, slots, taxonomy=taxonomy, today=today,
    )
    return result, facts


__all__ = []  # facade is internal; consumers import the private call intentionally
