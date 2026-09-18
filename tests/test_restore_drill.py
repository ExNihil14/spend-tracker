from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from spendtrack.doctor import run_checks
from spendtrack.store import Store

ROOT = Path(__file__).resolve().parents[1]


def _drill_module():
    spec = importlib.util.spec_from_file_location(
        "restore_drill", ROOT / "scripts" / "restore_drill.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _check(report: dict, check_id: str) -> dict:
    return next(c for c in report["checks"] if c["id"] == check_id)


def _make_db(path: Path, n: int = 2) -> None:
    store = Store(db_path=path)
    for i in range(n):
        store.add_transaction(date=f"2026-09-0{i + 1}", description=f"TX{i}",
                              amount_kopecks=-(i + 1) * 100, category="other",
                              category_source="manual")
    store.close()


def _snapshot(db: Path, target: Path) -> None:
    con = sqlite3.connect(db)
    try:
        quoted = str(target).replace("'", "''")
        con.execute(f"VACUUM INTO '{quoted}'")
    finally:
        con.close()


def _marker(bdir: Path, status: str = "ok", age_days: float = 0, **extra) -> Path:
    bdir.mkdir(parents=True, exist_ok=True)
    when = datetime.now(UTC) - timedelta(days=age_days)
    data = {"time": when.isoformat(timespec="seconds"), "file": "spend-x.db", "status": status}
    data.update(extra)
    path = bdir / "last_restore_drill.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ---- restore_drill.py ----
def test_latest_backup_picks_newest(tmp_path):
    bdir = tmp_path / "backup"
    bdir.mkdir()
    (bdir / "spend-20260917-000000.db").write_bytes(b"")
    newest = bdir / "spend-20260918-000000.db"
    newest.write_bytes(b"")
    assert _drill_module().latest_backup(bdir) == newest


def test_drill_ok_writes_marker(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 3)
    bdir = db.parent / "backup"
    bdir.mkdir()
    _snapshot(db, bdir / "spend-20260918-000000.db")

    result = _drill_module().run_restore_drill(db_path=db)
    assert result["status"] == "ok"
    assert result["integrity"] == "ok" and result["has_transactions"] is True
    assert result["count"] == 3 and result["count_match"] is True and result["sum_match"] is True

    data = json.loads((bdir / "last_restore_drill.json").read_text(encoding="utf-8"))
    assert data["status"] == "ok" and data["file"] == "spend-20260918-000000.db"


def test_drill_reports_divergence_informatively(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 2)
    bdir = db.parent / "backup"
    bdir.mkdir()
    _snapshot(db, bdir / "spend-20260918-000000.db")
    _make_db(db, 4)  # живая БД ушла вперёд — расхождение не ошибка

    result = _drill_module().run_restore_drill(db_path=db)
    assert result["status"] == "ok"
    assert result["count"] == 2 and result["live_count"] == 4
    assert result["count_match"] is False


def test_drill_failed_on_corrupt_backup(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    bdir = db.parent / "backup"
    bdir.mkdir()
    (bdir / "spend-20260918-000000.db").write_bytes(b"not a database")

    result = _drill_module().run_restore_drill(db_path=db)
    assert result["status"] == "failed"
    marker = json.loads((bdir / "last_restore_drill.json").read_text(encoding="utf-8"))
    assert marker["status"] == "failed"


def test_drill_failed_without_backups(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    result = _drill_module().run_restore_drill(db_path=db)
    assert result["status"] == "failed" and result["file"] is None


def test_drill_reads_only_temp_copy(tmp_path):
    """Восстановление идёт в копию: оригинал бэкапа не изменяется."""
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 2)
    bdir = db.parent / "backup"
    bdir.mkdir()
    backup = bdir / "spend-20260918-000000.db"
    _snapshot(db, backup)
    before = backup.read_bytes()

    assert _drill_module().run_restore_drill(db_path=db)["status"] == "ok"
    assert backup.read_bytes() == before


def test_drill_accepts_missing_live_db(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    bdir = db.parent / "backup"
    bdir.mkdir()
    _snapshot(db, bdir / "spend-20260918-000000.db")
    db.unlink()

    result = _drill_module().run_restore_drill(db_path=db)
    assert result["status"] == "ok" and "live_count" not in result


# ---- doctor check ----


def test_doctor_restore_missing_info(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    check = _check(run_checks(db), "restore_drill")
    assert check["severity"] == "info"


def test_doctor_restore_fresh_ok(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    _marker(db.parent / "backup", age_days=1)
    report = run_checks(db)
    check = _check(report, "restore_drill")
    assert report["status"] == "ok"
    assert check["severity"] == "ok" and "spend-x.db" in check["detail"]


def test_doctor_restore_stale_warn(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    _marker(db.parent / "backup", age_days=40)
    report = run_checks(db)
    check = _check(report, "restore_drill")
    assert report["status"] == "warn"
    assert check["severity"] == "warn" and "30" in check["detail"]


def test_doctor_restore_failed_critical(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    _marker(db.parent / "backup", status="failed", reason="снимок битый")
    report = run_checks(db)
    check = _check(report, "restore_drill")
    assert report["status"] == "critical" and check["severity"] == "critical"
    assert "failed" in check["detail"]


def test_doctor_restore_stale_with_non_utc_offset(tmp_path):
    """Маркер с не-UTC смещением не должен «омолаживаться» сменой tzinfo (черта 30 дней впритык)."""
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    bdir = db.parent / "backup"
    bdir.mkdir(parents=True, exist_ok=True)
    when = datetime.now(UTC) - timedelta(days=30, hours=1)
    tz = timezone(timedelta(hours=3))
    (bdir / "last_restore_drill.json").write_text(
        json.dumps({"time": when.astimezone(tz).isoformat(timespec="seconds"),
                    "file": "spend-x.db", "status": "ok"}, ensure_ascii=False),
        encoding="utf-8")

    check = _check(run_checks(db), "restore_drill")

    assert check["severity"] == "warn"


def test_doctor_restore_corrupt_marker_critical(tmp_path):
    db = tmp_path / "data" / "spend.db"
    _make_db(db, 1)
    bdir = db.parent / "backup"
    bdir.mkdir()
    (bdir / "last_restore_drill.json").write_text("{ broken", encoding="utf-8")
    check = _check(run_checks(db), "restore_drill")
    assert check["severity"] == "critical"
