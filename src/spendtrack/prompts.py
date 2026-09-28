from __future__ import annotations

from spendtrack.store import fmt_amount
from spendtrack.taxonomy import Taxonomy

_DESCRIPTION_LIMIT = 300


def _truncate(text: str, limit: int = _DESCRIPTION_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _examples_block(examples: list[dict]) -> str:
    if not examples:
        return (
            "- LIDL LIEFERUNG | -23.45 → {\"category\":\"groceries\",\"confidence\":0.97,\"merchant\":\"LIDL\",\"reason\":\"супермаркет\"}\n"
            "- UBER MUNCHEN | -12.00 → {\"category\":\"transport\",\"confidence\":0.95,\"merchant\":\"UBER\",\"reason\":\"такси\"}\n"
            "- ЗАРАБОТНАЯ ПЛАТА | +2500.00 → {\"category\":\"income\",\"confidence\":0.99,\"merchant\":\"ZP\",\"reason\":\"зарплата\"}"
        )

    lines = []
    for ex in examples:
        amt = fmt_amount(ex["amount_kopecks"])
        m = ex["description"].upper()[:20] or "UNKNOWN"
        cat = ex["category"]
        lines.append(
            f"- {_truncate(ex['description'])} | {amt} → "
            f'{{"category":"{cat}","confidence":0.98,"merchant":"{m}","reason":"пример"}}'
        )
    return "\n".join(lines)


def build_system_prompt(examples: list[dict], taxonomy: Taxonomy) -> str:
    categories = ", ".join(c.name for c in taxonomy.categories)
    return f"""Ты классификатор банковских транзакций. Возвращай ТОЛЬКО валидный JSON:
{{"category": "...", "confidence": 0.0-1.0, "merchant": "...", "reason": "..."}}

Категории: {categories}.
Правила:
- merchant = нормализованное имя (UPPER, обрезанное).
- income — ТОЛЬКО для поступлений (положительная сумма).
- Не уверен → "other" с низкой confidence.

ПРИМЕРЫ (few-shot из ваших исправлений):
{_examples_block(examples)}
"""


def build_user_prompt(tx: dict) -> str:
    amount = fmt_amount(tx["amount_kopecks"])
    return (
        f'description: "{_truncate(tx["description"])}"\n'
        f'amount: {amount}\n'
        f'account: "{tx.get("account_anon") or ""}"\n'
        f'date: "{tx["date"]}"'
    )