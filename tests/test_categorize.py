from __future__ import annotations

from spendtrack.categorize import _clamp_confidence, classify_with_injectable
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


def _stub_conf(value):
    return lambda t, s, tax: {
        "category": "groceries", "confidence": value, "merchant": "X", "reason": "r", "source": "llm"
    }


def test_confidence_above_one_is_clamped(store, taxonomy):
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf(1.5), 0.9)
    assert result["confidence"] == 1.0
    assert result["source"] == "llm"


def test_confidence_below_zero_is_clamped(store, taxonomy):
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf(-0.2), 0.9)
    assert result["confidence"] == 0.0
    assert result["source"] == "llm_pending_review"


def test_confidence_none_goes_queue(store, taxonomy):
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf(None), 0.9)
    assert result["confidence"] == 0.0
    assert result["source"] == "llm_pending_review"


def test_confidence_non_numeric_goes_queue(store, taxonomy):
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf("high"), 0.9)
    assert result["confidence"] == 0.0
    assert result["source"] == "llm_pending_review"


def test_clamp_confidence_edge_cases():
    assert _clamp_confidence(0.9) == 0.9
    assert _clamp_confidence("0.5") == 0.5
    assert _clamp_confidence(float("nan")) == 0.0
    assert _clamp_confidence(object()) == 0.0


def test_classify_commit_false_defers_merchant_cache(store, taxonomy):
    """commit=False (батч импорта): кэш мерчанта не коммитится посередине партии (ресёрч слоёв 23.09)."""
    def llm(tx, s, tax):
        return {"category": "restaurants", "confidence": 0.99, "merchant": "ДОДО",
                "reason": "stub", "source": "llm"}

    result = classify_with_injectable(_tx(), taxonomy, store, llm, 0.9, commit=False)
    assert result["source"] == "llm"
    assert store.conn.in_transaction is True  # запись кэша ждёт коммита партии
    store.conn.rollback()
    assert store.merchant_cache_get("ДОДО") is None

def test_parse_llm_json_rejects_non_dict():
    """Аудит 24.09: list/строка/число от LLM → None (иначе AttributeError роняет партию)."""
    from spendtrack.llm import parse_llm_json

    assert parse_llm_json("[]") is None
    assert parse_llm_json('"строка"') is None
    assert parse_llm_json("123") is None
    assert parse_llm_json('{"category": "food"}') == {"category": "food"}


def test_llm_null_merchant_does_not_crash(store, taxonomy):
    """merchant=null в ответе LLM не роняет классификацию (аудит 24.09)."""
    stub = lambda t, s, tax: {
        "category": "groceries", "confidence": 0.95, "merchant": None, "reason": "r", "source": "llm"
    }
    result = classify_with_injectable(_tx(), taxonomy, store, stub, 0.9)
    assert result["source"] == "llm" and result["category"] == "groceries"
