from __future__ import annotations

import sqlite3
import threading
import time

from spendtrack.store import Store, fingerprint

INSERT_HOLD = (
    "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
    " confidence, fingerprint, created, updated, review_status)"
    " VALUES('2026-09-01','HOLD',-100,'other','manual',1.0,'hold',?,?,'approved')"
)


def test_wal_pragmas_are_set(tmp_path):
    store = Store(db_path=tmp_path / "t.db")
    try:
        assert store.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert store.conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL при WAL
        assert store.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert store.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        store.close()


def test_second_writer_waits_for_uncommitted_first(tmp_path):
    """Второе соединение пишет, пока другое держит незакоммиченную транзакцию:
    busy_timeout ждёт освобождения, а не падает с 'database is locked'."""
    path = tmp_path / "c.db"
    Store(db_path=path).close()
    second = Store(db_path=path)
    stamp = "2026-09-01T00:00:00+00:00"
    locked = threading.Event()
    attempt = threading.Event()

    def holder():
        con = sqlite3.connect(path)
        try:
            con.execute(INSERT_HOLD, (stamp, stamp))  # транзакция открыта, commit не вызван
            locked.set()
            # commit строго после того, как второй писатель реально начнёт ждать (иначе флейк тайминга)
            assert attempt.wait(2)
            time.sleep(0.3)
            con.commit()
        finally:
            con.close()

    thread = threading.Thread(target=holder)
    thread.start()
    assert locked.wait(2)
    attempt.set()
    started = time.monotonic()
    try:
        second.add_transaction(date="2026-09-02", description="SECOND", amount_kopecks=-200,
                               category="other", category_source="manual")
    finally:
        elapsed = time.monotonic() - started
        thread.join()
        second.close()

    assert elapsed >= 0.15  # ждали чужой commit, а не упали сразу
    store = Store(db_path=path)
    try:
        descs = {r["description"] for r in store.conn.execute("SELECT description FROM transactions")}
    finally:
        store.close()
    assert descs == {"HOLD", "SECOND"}


def test_dedupe_race_returns_none_instead_of_integrity_error(tmp_path):
    """Гонка дедупа: устаревший пре-чек (строка ещё не закоммичена писателем) → None, а не падение.

    Регресс ревью Sonnet 5.5 (30.09): SELECT-затем-INSERT на UNIQUE(fingerprint) ронял партию
    импорта IntegrityError, если параллельно (CLI + UI) вставляли тот же отпечаток.
    """
    path = tmp_path / "race.db"
    Store(db_path=path).close()
    store = Store(db_path=path)
    stamp = "2026-09-01T00:00:00+00:00"
    fp = fingerprint("2026-09-01", -100, "HOLD", "", "", "RUB")
    locked = threading.Event()
    attempt = threading.Event()
    insert = (
        "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
        " confidence, fingerprint, created, updated, review_status, currency)"
        " VALUES('2026-09-01','HOLD',-100,'other','manual',1.0,?,?,?,'approved','RUB')"
    )

    def holder():
        con = sqlite3.connect(path)
        try:
            con.execute(insert, (fp, stamp, stamp))  # транзакция открыта, commit не вызван
            locked.set()
            assert attempt.wait(2)
            time.sleep(0.3)
            con.commit()
        finally:
            con.close()

    thread = threading.Thread(target=holder)
    thread.start()
    assert locked.wait(2)
    attempt.set()
    try:
        result = store.add_transaction(date="2026-09-01", description="HOLD", amount_kopecks=-100,
                                       category="other", category_source="manual")
    finally:
        thread.join()
        store.close()

    assert result is None  # тот же дедуп-исход, что при видимом дубле
