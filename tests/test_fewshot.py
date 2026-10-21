from __future__ import annotations

from spendtrack.categorize import classify_with_injectable
from spendtrack.store import parse_amount


def test_merchant_cache_hit_does_not_call_llm(store, taxonomy):
    """B-17 spend_tail #3: попадание в merchant_cache обязано исключить вызов LLM (жёсткий стаб).

    Красная сторона (адъюдикация wave10, мутант A): лишний вызов LLM ДО проверки кэша выживал
    на старом наборе (2 passed) — здесь он убивается: стаб падает, если его вообще позвали.
    """
    store.add_transaction(
        date="2026-09-01", description="SOME SHOP", amount_kopecks=parse_amount("-100"),
        category="groceries", category_source="correction", merchant="SOME SHOP",
        account_anon=None,
    )
    store.seed_merchant_cache(1)

    def forbidden(*_a, **_k):
        raise AssertionError("LLM не должен вызываться: merchant_cache выигрывает")

    result = classify_with_injectable(
        {"date": "2026-09-06", "description": "SOME SHOP", "amount_kopecks": parse_amount("-100")},
        taxonomy, store, forbidden, 0.9,
    )
    # кэш по мерчанту выигрывает, LLM не должен был решить иначе
    assert result["category"] == "groceries"
    assert result["source"] == "rule"


def test_low_conf_calls_llm_once_and_stays_uncached(store, taxonomy):
    """B-17 spend_tail #3: low-conf путь обязан вызвать LLM РОВНО один раз и не кэшировать.

    Красная сторона (мутант B): «мёртвая» low-conf ветка (без вызова, без записи) выживала
    на старом наборе — здесь она убивается счётчиком и проверкой результата ветки.
    """
    calls: list[dict] = []

    def stub(tx, s, tax):
        calls.append(dict(tx))
        return {"category": "household", "confidence": 0.3, "merchant": "UNCERTAIN",
                "source": "llm"}

    result = classify_with_injectable(
        {"date": "2026-09-06", "description": "UNCERTAIN", "amount_kopecks": parse_amount("-100")},
        taxonomy, store, stub, 0.9,
    )
    assert len(calls) == 1, f"LLM обязан вызываться ровно один раз (вызовов: {len(calls)})"
    assert result["source"] == "llm_pending_review"
    assert result["review_status"] == "pending"
    assert store.merchant_cache_get("UNCERTAIN") is None


def test_seed_merchant_cache_whitespace_merchant_falls_back_to_description(store):
    """B2 (ревью wave13): merchant=' ' не должен блокировать few-shot по описанию.

    Сеяние и лукап категоризатора используют `merchant or description`; whitespace-only
    merchant после strip пуст, поэтому ключом обязано стать описание (иначе кэш молча теряется).
    """
    store.add_transaction(
        date="2026-09-01", description="ПЯТЁРОЧКА", amount_kopecks=parse_amount("-100"),
        category="groceries", category_source="correction", merchant=" ",
        account_anon=None,
    )
    store.seed_merchant_cache(1)
    assert store.merchant_cache_get("ПЯТЁРОЧКА") == "groceries"


def test_whitespace_merchant_cache_lookup_falls_back_to_description(store, taxonomy):
    """B2 (ревью wave13), вторая половина: лукап тоже обязан игнорировать whitespace-merchant.

    Иначе seed кладёт ключ по описанию, а `categorize_rules_only` ищет ключ '' и идёт в LLM.
    """
    store.add_transaction(
        date="2026-09-01", description="ТЕСТОВЫЙ МАГАЗИН", amount_kopecks=parse_amount("-100"),
        category="groceries", category_source="correction", merchant=" ",
        account_anon=None,
    )
    store.seed_merchant_cache(1)

    def forbidden(*_a, **_k):
        raise AssertionError("LLM не должен вызываться: whitespace-merchant → описание в кэше")

    result = classify_with_injectable(
        {"date": "2026-09-06", "description": "ТЕСТОВЫЙ МАГАЗИН", "merchant": " ",
         "amount_kopecks": parse_amount("-100")},
        taxonomy, store, forbidden, 0.9,
    )
    assert result["category"] == "groceries"
    assert result["source"] == "rule"
