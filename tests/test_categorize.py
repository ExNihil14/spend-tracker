from __future__ import annotations

from spendtrack.categorize import classify_with_injectable
from spendtrack.store import parse_amount


def _tx(desc="STRANGE STORE", amount="-500"):
    return {"date": "2026-09-05", "description": desc, "amount_kopecks": parse_amount(amount), "merchant": desc[:20]}


def test_llm_valid_high_conf(store, taxonomy, sample_txs):
    stub = lambda t, s, tax: {
        "category": "groceries", "confidence": 0.95, "merchant": "STRANGE", "reason": "r", "source": "llm"
    }
    result = classify_with_injectable(_tx(), taxonomy, store, stub, 0.9)
    assert result["source"] == "llm"
    assert result["category"] == "groceries"


def test_llm_invalid_category_goes_queue(store, taxonomy):
    stub = lambda t, s, tax: {
        "category": "evil_cat", "confidence": 0.99, "merchant": "X", "reason": "r", "source": "llm"
    }
    result = classify_with_injectable(_tx(), taxonomy, store, stub, 0.9)
    # invalid категория не может быть принята
    assert result["category"] in {"other", "evil_cat"}
    assert result["source"] == "llm_pending_review"


def test_llm_low_conf_goes_queue(store, taxonomy):
    stub = lambda t, s, tax: {
        "category": "other", "confidence": 0.4, "merchant": "X", "reason": "uncertain", "source": "llm"
    }
    result = classify_with_injectable(_tx(), taxonomy, store, stub, 0.9)
    assert result["source"] == "llm_pending_review"
    assert result["confidence"] == 0.4


def test_rule_takes_priority_over_llm(store, taxonomy, sample_txs):
    """ЛЕНТА детектится правилом — LLM не вызывается."""
    stub = lambda t, s, tax: {"category": "entertainment", "confidence": 1.0, "merchant": None, "source": "llm"}
    result = classify_with_injectable(
        {"description": "ЛЕНТА new", "amount_kopecks": parse_amount("-100")}, taxonomy, store, stub, 0.9
    )
    assert result["source"] == "rule"
    assert result["category"] == "groceries"