"""C4: optional free-form LLM layer with redaction, fact-sheet-only prompts and number checks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from spendtrack.advisor.answer import Answer, answer
from spendtrack.advisor.facts import validate_facts
from spendtrack.advisor.slots import Slots
from spendtrack.store import fmt_amount
from spendtrack.taxonomy import Taxonomy, load_taxonomy

__all__ = ["Redaction", "ask", "redact_question"]

_REFUSAL = "По магазинам не отвечаю — только по категориям и периодам."
_FREEFORM_WORDS = ("почему", "что делать", "как сэконом", "совет", "рекоменд")
_SYSTEM = ("Ты — помощник по расходам. Отвечай только по фактам ниже, не выдумывай числа. "
           "Если данных нет — скажи об этом.")


@dataclass(frozen=True)
class Redaction:
    text: str
    hit: bool
    reasons: tuple[str, ...]


def redact_question(text: str, known_tokens: tuple[str, ...] = ()) -> Redaction:
    """Remove long digit runs and locally known merchant/description strings."""
    out = text or ""
    reasons = []
    cleaned = re.sub(r"\d{4,}", "<num>", out)
    if cleaned != out:
        reasons.append("digits")
    for token in sorted((t for t in known_tokens if t), key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)"
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(pattern, "<merchant>", cleaned, flags=re.IGNORECASE)
            reasons.append("merchant")
    return Redaction(cleaned, bool(reasons), tuple(sorted(set(reasons))))


def _needs_freeform(question: str, slots: Slots) -> bool:
    q = (question or "").lower()
    return slots.metric == "unknown" or any(w in q for w in _FREEFORM_WORDS)


def _prompt(question: str, facts: dict) -> str:
    return (_SYSTEM + "\n\nВопрос: " + question +
            "\n\nФакты (JSON, только агрегаты): " +
            json.dumps(facts, ensure_ascii=False, sort_keys=True))


def _amount_forms(kopecks: int) -> set[str]:
    raw = fmt_amount(int(kopecks))
    return {raw, raw.replace(".", ",")}


def _add_category(allowed: set[str], c: dict) -> None:
    allowed |= _amount_forms(c["sum"])
    allowed.add(str(c["count"]))
    allowed.add(f"{c['share_bp'] / 100:.1f}")
    allowed.add(f"{c['share_bp'] / 100:.1f}%")


def _add_budget(allowed: set[str], b: dict) -> None:
    for key in ("limit", "spent", "overrun"):
        allowed |= _amount_forms(b[key])
    if b["limit"] > 0:
        allowed.add(f"{b['spent'] * 100 / b['limit']:.0f}")


def _add_daily(allowed: set[str], d: dict) -> None:
    allowed.add(d["date"])
    allowed |= _amount_forms(d["sum"])


def _add_period(allowed: set[str], period: dict) -> None:
    for key in ("start", "end", "label", "month"):
        val = period.get(key)
        if val:
            allowed.add(str(val))


def _add_compare(allowed: set[str], cmp_: dict) -> None:
    if cmp_.get("total") is not None:
        allowed |= _amount_forms(cmp_["total"])
    if cmp_.get("label"):
        allowed.add(str(cmp_["label"]))


def _allowed_numbers(facts: dict) -> set[str]:
    allowed: set[str] = set()
    allowed |= _amount_forms(facts["total"])
    allowed.add(str(facts["tx_count"]))
    for c in facts.get("categories") or []:
        _add_category(allowed, c)
    for b in facts.get("budgets") or []:
        _add_budget(allowed, b)
    for d in facts.get("daily") or []:
        _add_daily(allowed, d)
    _add_period(allowed, facts.get("period") or {})
    _add_compare(allowed, facts.get("compare") or {})
    return allowed


def _numbers_ok(text: str, facts: dict) -> bool:
    allowed = _allowed_numbers(facts)
    return all(n in allowed for n in re.findall(r"\d+(?:[.,]\d+)?", text or ""))


def ask(question: str, facts: dict, slots: Slots,
        llm: Callable[[str], str] | None = None,
        taxonomy: Taxonomy | None = None,
        today: date | None = None,
        known_tokens: tuple[str, ...] = ()) -> Answer:
    """Template-first answer; free-form LLM only when explicitly injected and safe."""
    tx = taxonomy or load_taxonomy()
    template = answer(facts, slots, tx, today)
    if llm is None:
        return template
    red = redact_question(question, known_tokens)
    if red.hit:
        return Answer(_REFUSAL, "refusal", ())
    if not _needs_freeform(question, slots):
        return template
    try:
        validate_facts(facts, taxonomy=tx)
    except ValueError:
        return template
    try:
        text = llm(_prompt(red.text, facts))
    except Exception:  # noqa: BLE001 - LLM failure must fall back to the template
        return template
    if not text or not text.strip() or not _numbers_ok(text, facts):
        return template
    return Answer(text.strip(), "llm", ("facts",))
