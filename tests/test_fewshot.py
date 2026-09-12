from __future__ import annotations

from spendtrack.categorize import classify_with_injectable
from spendtrack.store import parse_amount


def test_merchant_cache_used_after_first_llm_call(store, taxonomy):
    store.add_transaction(
        date="2026-09-01", description="SOME SHOP", amount_kopecks=parse_amount("-100"),
        category="groceries", category_source="correction", merchant="SOME SHOP",
        account_anon=None,
    )
    store.seed_merchant_cache(1)

    stub = lambda t, s, tax: {"category": "household", "confidence": 0.99, "merchant": "SOME SHOP", "source": "llm"}
    result = classify_with_injectable(
        {"date": "2026-09-06", "description": "SOME SHOP", "amount_kopecks": parse_amount("-100")},
        taxonomy, store, stub, 0.9,
    )
    # кэш по мерчанту выигрывает, LLM не должен был решить иначе
    assert result["category"] == "groceries"
    assert result["source"] == "rule"


def test_low_conf_not_cached(store, taxonomy):
    stub = lambda t, s, tax: {"category": "household", "confidence": 0.3, "merchant": "UNCERTAIN", "source": "llm"}
    classify_with_injectable(
        {"date": "2026-09-06", "description": "UNCERTAIN", "amount_kopecks": parse_amount("-100")},
        taxonomy, store, stub, 0.9,
    )
    assert store.merchant_cache_get("UNCERTAIN") is None