"""C3 (03.10): ленивый бэкап на старте `serve` — свежесть, порог, выключение, безопасность.

Публичный интерфейс: `spendtrack.backup.lazy_backup_if_stale()` и `cli.main(["serve"])`.
"""
from __future__ import annotations

import os

import pytest

from spendtrack import cli
from spendtrack.backup import lazy_backup_if_stale, make_snapshot
from spendtrack.store import Store


@pytest.fixture()
def lazy_db(tmp_path, monkeypatch):
    db = tmp_path / "lazy.db"
    Store(db_path=db).close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    return db


def _snaps(db):
    d = db.parent / "backup" / db.stem
    return sorted(d.glob("spend-*.db")) if d.exists() else []


def test_lazy_creates_first_snapshot(lazy_db):
    """Нет снимков → создаётся один; повторный вызов видит свежий и не плодит копии."""
    res = lazy_backup_if_stale()
    assert res["status"] == "created" and str(res["file"]).startswith("spend-")
    assert len(_snaps(lazy_db)) == 1

    res2 = lazy_backup_if_stale()
    assert res2["status"] == "fresh"
    assert len(_snaps(lazy_db)) == 1


def test_lazy_respects_age_threshold(lazy_db):
    """Снимок старше недели → ленивый бэкап обновляет."""
    snap = make_snapshot(lazy_db)
    old = snap.stat().st_mtime - 8 * 24 * 3600  # 8 дней
    os.utime(snap, (old, old))

    res = lazy_backup_if_stale()
    assert res["status"] == "created"
    assert len(_snaps(lazy_db)) == 2


def test_lazy_can_be_disabled(lazy_db, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_LAZY_BACKUP_HOURS", "0")
    assert lazy_backup_if_stale()["status"] == "off"
    assert _snaps(lazy_db) == []


def test_lazy_missing_db_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "none.db"))
    assert lazy_backup_if_stale()["status"] == "skipped"


def test_serve_runs_lazy_backup(lazy_db, monkeypatch, capsys):
    """`spendtrack serve` делает ленивый бэкап до старта uvicorn (uvicorn подменён)."""
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert cli.main(["serve"]) == 0
    out = capsys.readouterr().out
    assert "ленивый бэкап" in out
    assert len(_snaps(lazy_db)) == 1


def test_serve_creates_db_before_lazy_backup(tmp_path, monkeypatch):
    """Wave6 ops_spend №5: serve на свежем каталоге создаёт БД ДО ленивого бэкапа — первый снимок есть."""
    import uvicorn

    db = tmp_path / "fresh.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert not db.exists()
    assert cli.main(["serve"]) == 0
    assert db.exists()  # БД создана (миграции прошли)
    assert len(_snaps(db)) == 1  # и ленивый бэкап успел сделать первый снимок


def test_lazy_never_raises_on_unexpected(monkeypatch, lazy_db):
    """Ревью wave5 (ops_spend №2): контракт «никогда не бросает» — любой сбой → failed."""
    from spendtrack import backup as B

    def _boom(db):
        raise ValueError("boom")

    monkeypatch.setattr(B, "find_snapshots", _boom)
    res = B.lazy_backup_if_stale()
    assert res["status"] == "failed" and "ValueError" in res["reason"]
