from __future__ import annotations

from datetime import date

from spendtrack.advisor.answer import Answer
from spendtrack.advisor.facts import Period
from spendtrack.advisor.llm import Redaction, ask, redact_question
from spendtrack.advisor.slots import Slots
from spendtrack.taxonomy import load_taxonomy

TODAY = date(2026, 10, 10)


def facts():
    return {
        "period": {"start": "2026-10-01", "end": "2026-10-31", "label": "2026-10",
                   "month": "2026-10"},
        "base_currency": "RUB",
        "total": 150_000,
        "tx_count": 3,
        "categories": [{"name": "groceries", "sum": 100_000, "count": 1,
                        "share_bp": 6667}],
        "budgets": [],
        "daily": [{"date": "2026-10-05", "sum": 100_000}],
        "excluded_foreign": {"count": 0, "currencies": []},
        "compare": {"total": 100_000, "daily": [], "label": "2026-09"},
        "unavailable": [],
    }


def slots(**kw):
    s = {"period": Period("2026-10-01", "2026-10-31", "2026-10", "2026-10"),
         "metric": "total", "category": None, "top_n": 3, "compare": False,
         "ask_back": None}
    s.update(kw)
    return Slots(**s)


class Spy:
    def __init__(self, reply="Всего 1500.00 ₽", exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.exc:
            raise self.exc
        return self.reply


def test_redact_digits():
    r = redact_question("сколько картой 4417?")
    assert isinstance(r, Redaction)
    assert r.hit and "<num>" in r.text and "4417" not in r.text


def test_redact_known_merchant():
    r = redact_question("сколько в магазин Пятёрочка", ("Пятёрочка",))
    assert r.hit and r.reasons == ("merchant",)
    assert "Пятёрочка" not in r.text and "<merchant>" in r.text


def test_redact_clean_question_unchanged():
    r = redact_question("сколько на продукты в этом месяце?")
    assert not r.hit and r.text == "сколько на продукты в этом месяце?"


def test_llm_not_called_for_plain_template():
    spy = Spy()
    a = ask("сколько потратил", facts(), slots(), spy, load_taxonomy(), TODAY)
    assert isinstance(a, Answer) and a.intent == "total" and spy.calls == []


def test_llm_called_for_advice_question():
    spy = Spy(reply="Всего 1500.00 ₽ — это выше прошлого периода.")
    a = ask("почему так много?", facts(), slots(), spy, load_taxonomy(), TODAY)
    assert a.intent == "llm" and len(spy.calls) == 1
    assert "merchant" not in spy.calls[0].lower()
    assert "description" not in spy.calls[0].lower()


def test_llm_unknown_uses_fact_number():
    spy = Spy(reply="Потрачено 1500.00 ₽.")
    s = slots(metric="unknown", ask_back="unknown")
    a = ask("что происходит?", facts(), s, spy, load_taxonomy(), TODAY)
    assert a.intent == "llm" and "1500.00" in a.text


def test_llm_invented_number_falls_back():
    spy = Spy(reply="Потрачено 999.00 ₽.")
    s = slots(metric="unknown", ask_back="unknown")
    a = ask("что происходит?", facts(), s, spy, load_taxonomy(), TODAY)
    assert a.intent == "ask_back" and "999" not in a.text


def test_llm_exception_falls_back():
    spy = Spy(exc=RuntimeError("down"))
    s = slots(metric="unknown", ask_back="unknown")
    a = ask("что происходит?", facts(), s, spy, load_taxonomy(), TODAY)
    assert a.intent == "ask_back"


def test_redaction_hit_refuses_without_llm():
    spy = Spy()
    s = slots(metric="unknown", ask_back="unknown")
    a = ask("сколько в Пятёрочка", facts(), s, spy, load_taxonomy(), TODAY,
            known_tokens=("Пятёрочка",))
    assert a.intent == "refusal" and spy.calls == []


def test_invalid_facts_fall_back():
    bad = facts()
    bad["merchant"] = "x"
    spy = Spy()
    a = ask("что происходит?", bad, slots(metric="unknown", ask_back="unknown"),
            spy, load_taxonomy(), TODAY)
    assert a.intent == "ask_back" and spy.calls == []
