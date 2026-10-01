from __future__ import annotations

import errno
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

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


def test_migration_takes_pre_snapshot(tmp_path):
    """Ревью install_ops (C1): апгрейд существующей БД оставляет pre-migration-снимок вне ротации."""
    db = tmp_path / "pre.db"
    _legacy_db(db, 3, rows=[("fp1", "2026-09-01", "ЛЕНТА", -100, "groceries", "rule", 1.0, "approved", 0)])

    s = Store(db_path=db)
    try:
        snaps = sorted((tmp_path / "backup").glob("pre-migration-v3-spend-*.db"))
        assert len(snaps) == 1, [p.name for p in (tmp_path / "backup").glob("*")]
        con = sqlite3.connect(snaps[0])
        try:
            assert con.execute("PRAGMA user_version").fetchone()[0] == 3  # снимок — ровно «до миграции»
            assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
        finally:
            con.close()
    finally:
        s.close()
    # повторное открытие (версия актуальна) снимков НЕ делает
    s2 = Store(db_path=db)
    s2.close()
    assert len(list((tmp_path / "backup").glob("pre-migration-*"))) == 1


def test_pre_migration_snapshot_replaces_stale_target(tmp_path, monkeypatch):
    """Ревью Dash 4.6: на Windows `rename` не перезаписывает существующий файл — снимок «терялся».

    Эмулируем семантику Windows (`Path.rename` → FileExistsError на существующем target) и фиксируем
    время снимка: корректный код использует replace, pre-migration-файл встаёт на место.
    """
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 1, 12, 0, 0, tzinfo=tz)

    def _windows_rename(self, target):
        target = Path(target)
        if target.exists():
            raise FileExistsError(errno.EEXIST, "File exists", str(target))
        return os.rename(self, target)

    monkeypatch.setattr("spendtrack.backup.datetime", _FrozenDatetime)
    monkeypatch.setattr(Path, "rename", _windows_rename)

    db = tmp_path / "pre.db"
    _legacy_db(db, 3, rows=[("fp1", "2026-09-01", "ЛЕНТА", -100, "groceries", "rule", 1.0,
                             "approved", 0)])
    backups = tmp_path / "backup"
    backups.mkdir()
    stale = backups / "pre-migration-v3-spend-20260901-120000.db"
    stale.write_text("старый файл", encoding="utf-8")

    Store(db_path=db).close()

    assert stale.read_bytes().startswith(b"SQLite format 3")  # цель перезаписана снимком
    con = sqlite3.connect(stale)
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 3  # снимок — «до миграции»
    finally:
        con.close()
    assert list(backups.glob("spend-*.db")) == []  # снимок не остался под сырым именем


def test_partial_v2_state_heals_without_duplicate_column(tmp_path):
    """Сбой посреди миграции v2 (category_llm уже добавлена, review_status — нет) не ломает открытие.

    Регресс ревью Sonnet 5.5 (30.09): старый код на повторе падал `duplicate column name` и БД
    становилась неоткрываемой; гарды по каждой колонке + транзакция лечат частичное состояние.
    """
    db = tmp_path / "partial.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
        merchant TEXT, account_anon TEXT, export_rowid TEXT,
        description TEXT NOT NULL, amount_kopecks INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT 'other', category_source TEXT NOT NULL DEFAULT 'rule',
        confidence REAL NOT NULL DEFAULT 1.0,
        llm_pending_review INTEGER NOT NULL DEFAULT 0, created TEXT, updated TEXT,
        category_llm TEXT)""")  # ← частичная миграция: review_status отсутствует
    conn.execute("INSERT INTO transactions (fingerprint, date, description, amount_kopecks,"
                 " category, category_source, confidence, llm_pending_review, category_llm)"
                 " VALUES ('fp1','2026-09-01','ЛЕНТА',-100,'groceries','llm_pending_review',0.4,1,'other')")
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    conn.execute("INSERT INTO schema_migrations VALUES (1,'2026-09-01T00:00:00+00:00')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    s = Store(db_path=db)
    try:
        assert s.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        cols = {r[1] for r in s.conn.execute("PRAGMA table_info(transactions)")}
        assert {"category_llm", "review_status", "statement_order", "currency"} <= cols
        row = s.conn.execute("SELECT review_status, category_llm FROM transactions WHERE id=1").fetchone()
        assert row["review_status"] == "pending"  # бэкфилл при лечении частичного состояния
        assert row["category_llm"] == "other"     # прежнее значение не перетёрто
    finally:
        s.close()


def test_db_newer_than_app_refuses_to_open(tmp_path):
    """БД новее приложения — явный отказ (ревью Sonnet 5.5): старый код молча писал в незнакомую схему."""
    db = tmp_path / "newer.db"
    Store(db_path=db).close()
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="новее приложения"):
        Store(db_path=db)


def test_failed_init_closes_connection(tmp_path, monkeypatch):
    """Сбой миграции при открытии не оставляет открытое соединение (утечка на каждый неудачный старт)."""
    captured: dict = {}
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        captured["conn"] = conn
        return conn

    monkeypatch.setattr("spendtrack.store.sqlite3.connect", spy)

    def boom(self):
        raise RuntimeError("миграция сломалась")

    monkeypatch.setattr(Store, "_migrate", boom)
    with pytest.raises(RuntimeError, match="миграция сломалась"):
        Store(db_path=tmp_path / "init-fail.db")

    with pytest.raises(sqlite3.ProgrammingError):
        captured["conn"].execute("SELECT 1")  # соединение закрыто, а не утекло


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
    cols = {r[1] for r in s.conn.execute("PRAGMA table_info(transactions)")}
    assert "statement_order" in cols
    s.close()


_V3_TABLE = """CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
    merchant TEXT, account_anon TEXT, export_rowid TEXT,
    description TEXT NOT NULL, amount_kopecks INTEGER NOT NULL,
    category TEXT NOT NULL DEFAULT 'other', category_source TEXT NOT NULL DEFAULT 'rule',
    confidence REAL NOT NULL DEFAULT 1.0,
    llm_pending_review INTEGER NOT NULL DEFAULT 0, created TEXT, updated TEXT,
    category_llm TEXT, review_status TEXT NOT NULL DEFAULT 'approved',
    statement_order INTEGER)"""


def _legacy_db(path, version: int, rows: list[tuple], budgets: list[tuple] | None = None):
    """Собирает БД «старой» версии: таблица transactions нужной формы + журнал миграций 1..version."""
    conn = sqlite3.connect(path)
    conn.executescript(_V3_TABLE)
    conn.executemany(
        "INSERT INTO transactions (fingerprint, date, description, amount_kopecks, category,"
        " category_source, confidence, review_status, statement_order)"
        " VALUES (?,?,?,?,?,?,?,?,?)", rows)
    if budgets is not None:
        conn.execute("CREATE TABLE budgets (category TEXT PRIMARY KEY,"
                     " amount_kopecks INTEGER NOT NULL)")
        conn.executemany("INSERT INTO budgets VALUES (?,?)", budgets)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY,"
                 " applied_at TEXT NOT NULL)")
    conn.executemany("INSERT INTO schema_migrations VALUES (?, '2026-09-01T00:00:00+00:00')",
                     [(v,) for v in range(1, version + 1)])
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


def _snapshot(store: Store) -> tuple:
    row = store.conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(amount_kopecks),0) s FROM transactions").fetchone()
    txs = [tuple(r) for r in store.conn.execute(
        "SELECT id, date, description, amount_kopecks, category, statement_order, currency"
        " FROM transactions ORDER BY id")]
    return (row["c"], row["s"], txs)


def test_v3_fixture_migrates_without_data_loss(tmp_path):
    """v3 (statement_order есть, currency нет): данные идентичны, currency='RUB' назадфиллена,
    повторное открытие идемпотентно (нет дублей и повторных миграций)."""
    db = tmp_path / "v3.db"
    rows = [("fp1", "2026-09-01", "ПЯТЁРОЧКА", -12345, "groceries", "rule", 1.0, "approved", 0),
            ("fp2", "2026-09-02", "ЗАРПЛАТА", 250000, "income", "rule", 1.0, "approved", 1)]
    _legacy_db(db, 3, rows)

    s = Store(db_path=db)
    try:
        assert s.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        snap1 = _snapshot(s)
        assert snap1[0] == 2 and snap1[1] == 237655
        assert all(t[6] == "RUB" for t in snap1[2])  # бэкфилл валюты
        assert [t[5] for t in snap1[2]] == [0, 1]    # statement_order не потерян
    finally:
        s.close()

    s2 = Store(db_path=db)
    try:
        assert _snapshot(s2) == snap1  # повторное открытие ничего не меняет
        assert s2.conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
    finally:
        s2.close()


def test_v4_fixture_preserves_budgets(tmp_path):
    """v4 (currency нет, бюджеты есть): бюджеты и строки переживают миграцию v5."""
    db = tmp_path / "v4.db"
    rows = [("fp1", "2026-09-03", "ЛЕНТА", -50000, "groceries", "rule", 1.0, "approved", 0)]
    _legacy_db(db, 4, rows, budgets=[("groceries", 1234500), ("restaurants", 300000)])

    s = Store(db_path=db)
    try:
        assert s.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        budgets = {r["category"]: r["amount_kopecks"] for r in
                   s.conn.execute("SELECT category, amount_kopecks FROM budgets")}
        assert budgets == {"groceries": 1234500, "restaurants": 300000}
        snap = _snapshot(s)
        assert snap[0] == 1 and snap[1] == -50000 and snap[2][0][6] == "RUB"
    finally:
        s.close()

    s2 = Store(db_path=db)
    try:
        assert _snapshot(s2)[0] == 1  # без дублей
        assert s2.conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0] == 2
    finally:
        s2.close()
