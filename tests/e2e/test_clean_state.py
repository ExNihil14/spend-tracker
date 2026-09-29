"""Инвариант clean_state: после очистки все пользовательские таблицы пусты (ревью tests_contour S5).

Раньше чистились только transactions/merchant_cache/import_batches — бюджеты, примеры и
псевдонимы счётов переживали тест (порядко-зависимые флейки и ложные зелёные).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from helpers import clean_state

from spendtrack.store import Store

KEEP = {"schema_migrations"}  # журнал миграций не чистим (идемпотентность апгрейд-пути)


def _tables(db: Path) -> list[str]:
    con = sqlite3.connect(db)
    try:
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    finally:
        con.close()


def test_clean_state_empties_all_user_tables(tmp_path):
    db = tmp_path / "t.db"
    store = Store(db_path=db)
    try:
        store.add_transaction(date="2026-09-10", description="ЛЕНТА", amount_kopecks=-10000,
                              category="groceries", category_source="rule",
                              account_anon="acc-x", export_rowid="r1")
        store.set_budget("groceries", 2_000_000)
        store.add_example("ЛЕНТА", -10000, "groceries")
    finally:
        store.close()

    clean_state(db)

    con = sqlite3.connect(db)
    try:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in _tables(db)}
    finally:
        con.close()
    leftovers = {t: n for t, n in counts.items() if n and t not in KEEP}
    assert leftovers == {}, f"после clean_state осталось: {leftovers}"
