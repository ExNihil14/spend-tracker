from __future__ import annotations

import logging

from spendtrack.config import load_settings
from spendtrack.llm import call_llm, parse_llm_json
from spendtrack.prompts import build_system_prompt, build_user_prompt
from spendtrack.store import Store
from spendtrack.taxonomy import Taxonomy

logger = logging.getLogger(__name__)


def categorize_rules_only(tx: dict, taxonomy: Taxonomy, store: Store) -> str | None:
    """Step 1: merchant cache → keyword rules. Возвращает category или None."""
    merchant = (tx.get("merchant") or tx["description"]).upper().strip()
    cached = store.merchant_cache_get(merchant)
    if cached and taxonomy.is_valid(cached):
        return cached

    desc_upper = tx["description"].upper()
    for rule in taxonomy.rules:
        if rule.pattern in desc_upper and taxonomy.is_valid(rule.category):
                return rule.category
    return None


def categorize_llm(tx: dict, store: Store, taxonomy: Taxonomy) -> dict:
    """Step 2: LLM-классификация. Возвращает {'category', 'confidence', 'merchant', 'reason', 'source'}."""
    examples = store.list_examples()
    system_prompt = build_system_prompt(examples)
    user_prompt = build_user_prompt(tx)

    llm_result = call_llm(system_prompt, user_prompt, max_tokens=400)
    parsed = parse_llm_json(llm_result["content"])

    if not parsed or not taxonomy.is_valid(parsed.get("category", "")):
        return {"category": "other", "confidence": 0.0, "merchant": tx.get("merchant"),
                "reason": "llm_parse_failed", "source": "llm"}

    confidence = float(parsed.get("confidence", 0.0))
    merchant_norm = parsed.get("merchant", "").upper().strip() or tx.get("merchant")
    return {
        "category": parsed["category"],
        "confidence": confidence,
        "merchant": merchant_norm,
        "reason": parsed.get("reason", ""),
        "source": "llm",
    }


def classify_with_injectable(
    tx: dict, taxonomy: Taxonomy, store: Store, llm_getter, acceptance: float
) -> dict:
    """Тестируемая версия: llm_getter — функция (tx, store, taxonomy) -> dict.

    Возвращает dict с category/source/confidence/merchant, где источник rule|llm|llm_pending_review.
    """
    rule_result = categorize_rules_only(tx, taxonomy, store)
    if rule_result:
        return {"category": rule_result, "confidence": 1.0, "merchant": tx.get("merchant"),
                "reason": "keyword_rule", "source": "rule"}

    llm_result = llm_getter(tx, store, taxonomy)
    conf = float(llm_result.get("confidence", 0.0))
    cat = llm_result.get("category", "")
    bucket = f"{int(conf * 10) / 10:.1f}"
    logger.info("llm_decision: conf=%.3f bucket=%s accepted=%s desc=%s",
                conf, bucket, conf >= acceptance, tx.get("description", "")[:40])
    if not taxonomy.is_valid(cat):
        llm_result.update({"category": "other", "confidence": 0.0, "source": "llm_pending_review"})
        return llm_result
    if conf >= acceptance:
        llm_result["source"] = "llm"
        if llm_result.get("merchant"):
            store.merchant_cache_set(llm_result["merchant"], llm_result["category"])
        return llm_result

    llm_result["source"] = "llm_pending_review"
    return llm_result


def categorize_transaction(tx: dict, taxonomy: Taxonomy, store: Store) -> dict:
    """Полный пайплайн (боевой): rule → merchant-cache → LLM → validation → queue."""
    settings = load_settings()
    return classify_with_injectable(
        tx, taxonomy, store,
        lambda t, s, tax: categorize_llm(t, s, tax),
        settings.acceptance.auto_accept_confidence,
    )