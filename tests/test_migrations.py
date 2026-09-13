from __future__ import annotations

import sqlite3

from spendtrack.store import SCHEMA_VERSION, Store


def test_fresh_db_versioned(tmp_path):
    s = Store(db_path=tmp_path / "m.db")
    assert s.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    versions = [r[0] for r in s.conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions == list(range(1, SCHEMA_VERSION + 1))
    s.close()


def test_reopen_is_idempotent(tmp_path):
    db = tmp_path / "m.db"
    s = Store(db_path=db)
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="rule")
    s.close()
    s2 = Store(db_path=db)
    assert s2.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert s2.conn.execute("SELECT COUNT(1) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
    s2.close()


def test_legacy_db_upgraded_with_backfill(tmp_path):
    """Старая схема (без review_status) → миграция v2 + бэкфилл, версия и журнал выставлены."""
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
        merchant TEXT, account_anon TEXT, export_rowid TEXT,
        description TEXT NOT NULL, amount_kopecks INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT 'other', category_source TEXT NOT NULL DEFAULT 'rule',
        confidence REAL NOT NULL DEFAULT 1.0,
        llm_pending_review INTEGER NOT NULL DEFAULT 0, created TEXT, updated TEXT)""")
    conn.execute("INSERT INTO transactions (fingerprint, date, description, amount_kopecks,"
                 " category, category_source, confidence, llm_pending_review)"
                 " VALUES ('fp1','2026-09-01','СТАРЫЙ',-100,'other','llm_pending_review',0.3,1)")
    conn.commit()
    conn.close()

    s = Store(db_path=db)
    assert s.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    row = s.conn.execute("SELECT review_status, category_llm FROM transactions WHERE id=1").fetchone()
    assert row["review_status"] == "pending"
    assert row["category_llm"] == "other"
    s.close()
