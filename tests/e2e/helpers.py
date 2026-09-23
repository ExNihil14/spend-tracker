"""Общие seed-хелперы e2e: данные через публичный Store (не raw SQL) — тесты не разъезжаются со схемой.

Аудит тестирования 23.09 (P2): дедуп seed-хелперов (`_seed_pending`/`_seed`/`_seed_txs` были
raw-SQL копиями с разными подписями).
"""
from __future__ import annotations

from pathlib import Path

from spendtrack.store import Store


def seed_tx(db_path: str | Path, date: str, description: str, kopecks: int, *,
            category: str = "groceries", category_source: str = "rule", **kwargs) -> None:
    """Одна операция через Store (kwargs — поля add_transaction: currency, merchant и т.п.)."""
    store = Store(db_path=Path(db_path))
    try:
        store.add_transaction(date=date, description=description, amount_kopecks=kopecks,
                              category=category, category_source=category_source, **kwargs)
    finally:
        store.close()


def seed_pending(db_path: str | Path, rows: list[tuple]) -> None:
    """Очередь подтверждения (обход LLM): строки (fp, date, desc, kopecks, conf, llm_cat).

    `fp` в сигнатуре оставлен для совместимости вызовов — Store считает fingerprint сам.
    """
    store = Store(db_path=Path(db_path))
    try:
        for _fp, day, desc, kopecks, conf, llm_cat in rows:
            store.add_transaction(date=day, description=desc, amount_kopecks=kopecks,
                                  category="other", category_source="llm_pending_review",
                                  confidence=conf, category_llm=llm_cat,
                                  review_status="pending")
    finally:
        store.close()


def seed_smoke_data(db_path: str | Path, n: int = 6) -> None:
    """Данные для кросс-движкового смоука: графики/таблицы непусты + 2 строки очереди."""
    store = Store(db_path=Path(db_path))
    try:
        for i in range(n):
            store.add_transaction(
                date=f"2026-09-{10 + i:02d}", description=f"МАГАЗИН {i}",
                amount_kopecks=-(10_000 + i * 1_000), category="groceries",
                category_source="import", export_rowid=f"smoke-{i}", merchant=f"МАГАЗИН {i}",
                statement_order=i)
        for i in range(2):
            store.add_transaction(
                date=f"2026-09-{20 + i:02d}", description=f"НЕИЗВЕСТНЫЙ {i}",
                amount_kopecks=-(20_000 + i * 500), category="other",
                category_source="llm_pending_review", export_rowid=f"smoke-pending-{i}",
                merchant=f"НЕИЗВЕСТНЫЙ {i}", category_llm="other", review_status="pending")
    finally:
        store.close()
