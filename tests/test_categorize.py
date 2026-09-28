from __future__ import annotations

from spendtrack.categorize import _clamp_confidence, categorize_rules_only, classify_with_injectable
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


def test_llm_low_conf_does_not_write_guess_into_category(store, taxonomy):
    """C4 (ревью 28.09): гипотеза при низкой уверенности живёт в category_llm, не в боевом category."""
    stub = lambda t, s, tax: {
        "category": "restaurants", "confidence": 0.4, "merchant": "X", "reason": "r", "source": "llm"
    }
    result = classify_with_injectable(_tx(), taxonomy, store, stub, 0.9)
    assert result["review_status"] == "pending"
    assert result["category"] == "other"
    assert result["category_llm"] == "restaurants"


def test_llm_income_on_outflow_goes_queue(store, taxonomy):
    """S6: income на расходной операции — авто-приём запрещён, гипотеза уходит в очередь."""
    stub = lambda t, s, tax: {
        "category": "income", "confidence": 0.95, "merchant": "X", "reason": "r", "source": "llm"
    }
    result = classify_with_injectable(_tx(), taxonomy, store, stub, 0.9)
    assert result["source"] == "llm_pending_review"
    assert result["category"] == "other"
    assert result["category_llm"] == "income"


def test_rule_takes_priority_over_llm(store, taxonomy, sample_txs):
    """ЛЕНТА детектится правилом — LLM не вызывается."""
    stub = lambda t, s, tax: {"category": "entertainment", "confidence": 1.0, "merchant": None, "source": "llm"}
    result = classify_with_injectable(
        {"description": "ЛЕНТА new", "amount_kopecks": parse_amount("-100")}, taxonomy, store, stub, 0.9
    )
    assert result["source"] == "rule"
    assert result["category"] == "groceries"


def test_income_rule_skipped_for_outflow(store, taxonomy):
    """S6 (ревью 28.09): keyword-правило income не применяется к расходной операции."""
    got = categorize_rules_only(
        {"description": "ЗАРАБОТНАЯ ПЛАТА", "amount_kopecks": parse_amount("-50000")}, taxonomy, store)
    assert got is None


def test_salary_transfer_positive_is_income(store, taxonomy):
    """S6: «ПЕРЕВОД ЗАРАБОТНОЙ ПЛАТЫ» — доход (income-правила выше transfers), а не перевод."""
    got = categorize_rules_only(
        {"description": "ПЕРЕВОД ЗАРАБОТНОЙ ПЛАТЫ", "amount_kopecks": parse_amount("120000")},
        taxonomy, store)
    assert got == "income"


def test_rules_match_merchant_field_too(store, taxonomy):
    """S7: правила смотрят и на merchant — банки кладут имя ТСП в отдельное поле."""
    got = categorize_rules_only(
        {"description": "Покупка товаров и услуг", "merchant": "ЛЕНТА",
         "amount_kopecks": parse_amount("-500")}, taxonomy, store)
    assert got == "groceries"


def _stub_conf(value):
    return lambda t, s, tax: {
        "category": "groceries", "confidence": value, "merchant": "X", "reason": "r", "source": "llm"
    }


def test_confidence_above_one_goes_queue(store, taxonomy):
    """S12: значение вне [0,1] — сломанный вывод, авто-приём запрещён (было: clamp до 1.0)."""
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf(1.5), 0.9)
    assert result["confidence"] == 0.0
    assert result["source"] == "llm_pending_review"


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


def test_confidence_bool_goes_queue(store, taxonomy):
    """S12: bool — не уверенность (float(True)=1.0 не должен давать авто-приём)."""
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf(True), 0.9)
    assert result["confidence"] == 0.0
    assert result["source"] == "llm_pending_review"


def test_confidence_inf_goes_queue(store, taxonomy):
    """S12: inf (json.loads принимает 1e400/Infinity) — сломанный вывод, не авто-приём."""
    result = classify_with_injectable(_tx(), taxonomy, store, _stub_conf(float("inf")), 0.9)
    assert result["confidence"] == 0.0
    assert result["source"] == "llm_pending_review"


def test_clamp_confidence_edge_cases():
    assert _clamp_confidence(0.9) == 0.9
    assert _clamp_confidence("0.5") == 0.5
    assert _clamp_confidence(float("nan")) == 0.0
    assert _clamp_confidence(float("inf")) == 0.0
    assert _clamp_confidence(True) == 0.0
    assert _clamp_confidence(1.5) == 0.0
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


def test_llm_decision_log_does_not_leak_description(store, taxonomy, caplog):
    """S8 (ревью 28.09): INFO-лог решения не содержит сырого описания (приватность офлайн-first)."""
    import logging

    secret = "ОПЛАТА ОТ ИВАНОВ И.И. 4276"
    stub = lambda t, s, tax: {
        "category": "groceries", "confidence": 0.95, "merchant": "X", "reason": "r", "source": "llm"
    }
    with caplog.at_level(logging.INFO, logger="spendtrack.categorize"):
        classify_with_injectable(_tx(desc=secret), taxonomy, store, stub, 0.9)
    assert all(secret not in r.getMessage() for r in caplog.records if r.levelno >= logging.INFO)
