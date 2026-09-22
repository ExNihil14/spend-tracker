"""FastAPI-зависимость жизненного цикла SQLite: одно соединение на запрос, закрытие гарантировано.

FastAPI выполняет sync-зависимости и sync-роуты в threadpool (потоки могут различаться), поэтому
`Store` открывает SQLite с `check_same_thread=False` (как в официальном примере FastAPI).
Закрытие — в `finally` после ответа: без этого соединения (и WAL-reader'ы) копились бы до GC.
"""
from __future__ import annotations

from collections.abc import Iterator

from spendtrack.store import Store


def get_store() -> Iterator[Store]:
    """Соединение на запрос: `yield` + гарантированный `close()` (FastAPI dependency)."""
    store = Store()
    try:
        yield store
    finally:
        store.close()
