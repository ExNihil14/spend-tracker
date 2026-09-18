from __future__ import annotations

import sqlite3
import threading
import time

from spendtrack.store import Store

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
