from __future__ import annotations

import pytest

from spendtrack.store import parse_amount


@pytest.mark.perf
def test_bulk_insert_1000(store, taxonomy):
    """Вставка 1000 транзакций без LLM (только правила).

    Сантити-порог защищает от падения производительности; детальная
    длительность уходит в reports/perf.json через perf-marker.
    """
    for i in range(1000):
        store.add_transaction(
            date="2026-09-01",
            description=f"СТРОЙМАРКЕТ-{i}",
            amount_kopecks=parse_amount("-100.00"),
            category="household",
            category_source="rule",
            confidence=1.0,
            merchant=f"СТРОЙМАРКЕТ-{i}",
            account_anon="acc_test",
            export_rowid="",
        )
    assert store.counts()["rule"] == 1000


@pytest.mark.perf
def test_digest_20k_synthetic(tmp_path):
    """Аналитика дашборда на 20K строк: сантим-порог (ловушка на двойной расчёт подписок)."""
    import importlib.util
    import time
    from pathlib import Path

    from spendtrack.digest import build_digest
    from spendtrack.store import Store

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bench", root / "scripts" / "bench.py")
    bench = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(bench)

    db_path = tmp_path / "bench.db"
    bench.seed(db_path, 20_000)  # публичный сидер бенча (env не трогает)
    store = Store(db_path=db_path)
    try:
        build_digest(store)  # warmup: кэши sqlite
        t0 = time.perf_counter()
        digest = build_digest(store)
        elapsed = time.perf_counter() - t0
    finally:
        store.close()

    assert digest["transaction_count"] >= 0
    assert elapsed < 2.0, f"build_digest на 20K занял {elapsed:.2f}s (порог 2.0s)"
