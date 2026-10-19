"""B2/N1 (письмо 0005, волна 14): whitespace-мерчант — strip-first во всех путях кэша.

Регресс на пути: ключ get/set, лукап categorize.py:36, few-shot seed, массовое одобрение
(approve_all_reviews) и сверка doctor'а. Красная сторона: «   » как merchant не ронялось до
пустого (или ронялось несогласованно), ключи записи/чтения расходились, doctor ложно репортил
живые записи мёртвыми.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from spendtrack.categorize import categorize_rules_only
from spendtrack.doctor import run_checks
from spendtrack.store import Store

DESC = "КРАЙ-ТЕСТ-98"  # синтетика: в config/taxonomy.toml правил с таким паттерном нет


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "data" / "spend.db"
    Store(path).close()
    return path


def _check(report: dict, check_id: str) -> dict:
    return next(c for c in report["checks"] if c["id"] == check_id)


def test_cache_key_strip_first_roundtrip(store):
    """N1: запись с краевыми пробелами читается по нормализованному имени (единый `_cache_key`)."""
    store.merchant_cache_set("  ЛЕНТА  ", "groceries")
    assert store.merchant_cache_get("ЛЕНТА") == "groceries"


def test_lookup_whitespace_merchant_falls_back_to_description(store, taxonomy):
    """N1 (categorize.py:36): whitespace-мерчант не перекрывает описание — кэш по DESC найден."""
    store.merchant_cache_set(DESC, "groceries")
    tx = {"date": "2026-10-01", "description": DESC, "amount_kopecks": -100, "merchant": "   "}
    assert categorize_rules_only(tx, taxonomy, store) == "groceries"


def test_seed_whitespace_merchant_falls_back_to_description(store):
    """B2: подтверждение строки с whitespace-мерчантом учит кэш по описанию, а не молчит."""
    tx_id = store.add_transaction(date="2026-10-01", description=DESC, amount_kopecks=-100,
                                  category="groceries", category_source="correction",
                                  merchant="   ")
    store.seed_merchant_cache(tx_id)
    assert store.merchant_cache_get(DESC) == "groceries"


def test_approve_all_reviews_whitespace_merchant_adds_no_dead_key(db_path):
    """B2 (store.py:752-756): массовое одобрение не сажает нечитаемый ключ от «   »."""
    store = Store(db_path)
    store.add_transaction(date="2026-10-01", description=DESC, amount_kopecks=-100,
                          category="groceries", category_source="llm_pending_review",
                          merchant="   ", review_status="pending")
    assert store.approve_all_reviews() == 1
    store.close()
    assert _check(run_checks(db_path), "merchant_cache_dead")["count"] == 0


def test_doctor_whitespace_merchant_keeps_description_key_alive(db_path):
    """B2 (doctor.py:165-174): строка с whitespace-мерчантом держит ключ по описанию живым."""
    store = Store(db_path)
    store.add_transaction(date="2026-09-10", description=DESC, amount_kopecks=-100,
                          category="other", category_source="manual", merchant="   ")
    store.merchant_cache_set(DESC, "other")
    store.close()
    assert _check(run_checks(db_path), "merchant_cache_dead")["severity"] == "ok"
