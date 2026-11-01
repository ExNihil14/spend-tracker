"""Frozen Phase C contract: protocol + stub integration test."""
from __future__ import annotations

import inspect
from datetime import date

from spendtrack.advisor.answer import Answer
from spendtrack.advisor.contract import (
    PHASE_C_CONTRACT_VERSION,
    AdvisorProtocol,
    TemplateAdvisor,
    run_advisor_flow,
)
from spendtrack.advisor.facts import Period
from spendtrack.advisor.slots import Slots
from spendtrack.taxonomy import load_taxonomy

TODAY = date(2026, 10, 10)


def facts() -> dict:
    return {
        "period": {"start": "2026-10-01", "end": "2026-10-31", "label": "2026-10",
                   "month": "2026-10"},
        "base_currency": "RUB",
        "total": 150_000,
        "tx_count": 3,
        "categories": [],
        "budgets": [],
        "daily": [],
        "excluded_foreign": {"count": 0, "currencies": []},
        "compare": None,
        "unavailable": [],
    }


def slots() -> Slots:
    return Slots(Period("2026-10-01", "2026-10-31", "2026-10", "2026-10"),
                 "total", None, 3, False, None)


class StubAdvisor:
    """Test double: implements the frozen call surface, no internals."""

    def ask(self, question, facts, slots, llm=None, taxonomy=None, today=None,
            known_tokens=None) -> Answer:
        return Answer("stub answer", "stub", ())


def test_contract_version_and_adapters_implement_protocol() -> None:
    assert PHASE_C_CONTRACT_VERSION == "1"
    assert isinstance(TemplateAdvisor(), AdvisorProtocol)
    assert isinstance(StubAdvisor(), AdvisorProtocol)


def test_frozen_signature_is_explicit() -> None:
    expected = ["self", "question", "facts", "slots", "llm", "taxonomy", "today", "known_tokens"]
    assert list(inspect.signature(AdvisorProtocol.ask).parameters) == expected
    assert list(inspect.signature(TemplateAdvisor.ask).parameters) == expected


def test_stub_and_live_adapter_complete_the_same_flow_surface() -> None:
    stub = run_advisor_flow(StubAdvisor(), "q", facts(), slots(), taxonomy=load_taxonomy(), today=TODAY)
    live = run_advisor_flow(TemplateAdvisor(), "сколько потратил", facts(), slots(),
                            taxonomy=load_taxonomy(), today=TODAY, known_tokens=())
    assert isinstance(stub, Answer) and stub.text == "stub answer"
    assert isinstance(live, Answer) and live.intent == "total"
