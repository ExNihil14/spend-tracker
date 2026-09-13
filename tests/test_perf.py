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