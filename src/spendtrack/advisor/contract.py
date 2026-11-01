"""Frozen Phase C advisor boundary (contract v1).

Integration must import only this module, not the internal facts/slots/llm modules.
Any breaking change to the protocol bumps PHASE_C_CONTRACT_VERSION and updates the adapter.

Enforcement status: `cli.py` consumes `advisor.integration._answer_question` (facade), and
`tests/test_advisor_contract.py` statically rejects direct facts/slots/llm imports in that
consumer. The facade itself is the only internal-import seam; new PWA/integration code must use
`run_advisor_flow`/`AdvisorProtocol`.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Protocol, runtime_checkable

from spendtrack.advisor.answer import Answer
from spendtrack.advisor.llm import ask as _ask
from spendtrack.advisor.slots import Slots
from spendtrack.taxonomy import Taxonomy

__all__ = [
    "PHASE_C_CONTRACT_VERSION",
    "AdvisorProtocol",
    "TemplateAdvisor",
    "run_advisor_flow",
]

PHASE_C_CONTRACT_VERSION = "1"


@runtime_checkable
class AdvisorProtocol(Protocol):
    """Contract for the advisor call used by Phase C integration/PWA."""

    def ask(
        self,
        question: str,
        facts: dict,
        slots: Slots,
        llm: Callable[[str], str] | None = None,
        taxonomy: Taxonomy | None = None,
        today: date | None = None,
        known_tokens: tuple[str, ...] | None = None,
    ) -> Answer: ...


class TemplateAdvisor:
    """Default live adapter: template-first advisor with the existing LLM seam."""

    def ask(
        self,
        question: str,
        facts: dict,
        slots: Slots,
        llm: Callable[[str], str] | None = None,
        taxonomy: Taxonomy | None = None,
        today: date | None = None,
        known_tokens: tuple[str, ...] | None = None,
    ) -> Answer:
        return _ask(question, facts, slots, llm=llm, taxonomy=taxonomy, today=today,
                    known_tokens=known_tokens)


def run_advisor_flow(
    advisor: AdvisorProtocol,
    question: str,
    facts: dict,
    slots: Slots,
    *,
    llm: Callable[[str], str] | None = None,
    taxonomy: Taxonomy | None = None,
    today: date | None = None,
    known_tokens: tuple[str, ...] | None = None,
) -> Answer:
    """Integration entrypoint: only the frozen protocol is used here."""
    return advisor.ask(question, facts, slots, llm=llm, taxonomy=taxonomy, today=today,
                       known_tokens=known_tokens)
