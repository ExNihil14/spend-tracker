"""Restore-drill: проверка, что свежий бэкап реально восстанавливается и читается.

Берёт последний `data/backup/spend-*.db` (бэкапы — `VACUUM INTO`-снимки, консистентные
одиночные файлы без `-wal`/`-shm`), копирует во временную папку, прогоняет
`PRAGMA integrity_check`, проверяет таблицу `transactions` и `user_version`, сверяет
COUNT/SUM(amount_kopecks) с живой БД информативно (расхождение из-за новых транзакций —
не ошибка) и пишет маркер `data/backup/last_restore_drill.json` для doctor-чека.

Использование:
    uv run python -m scripts.restore_drill
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.config import ROOT, load_settings

MARKER_NAME = "last_restore_drill.json"


def latest_backup(backup_dir: Path) -> Path | None:
    files = sorted(backup_dir.glob("spend-*.db"), key=lambda p: (p.stat().st_mtime, p.name))
    return files[-1] if files else None


def inspect_db(path: Path) -> dict:
    """Читает снимок read-only: integrity_check, transactions, user_version, COUNT/SUM."""
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        has_tx = bool(con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()[0])
        user_version = int(con.execute("PRAGMA user_version").fetchone()[0])
        if has_tx:
            count = int(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
            total = int(con.execute(
                "SELECT COALESCE(SUM(amount_kopecks), 0) FROM transactions").fetchone()[0])
        else:
            count, total = 0, 0
    finally:
        con.close()
    return {"integrity": integrity, "has_transactions": has_tx,
            "user_version": user_version, "count": count, "sum_kopecks": total}


def live_stats(path: Path) -> dict | None:
    if not path.exists():
        return None
    con = sqlite3.connect(path)
    try:
        count = int(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
        total = int(con.execute(
            "SELECT COALESCE(SUM(amount_kopecks), 0) FROM transactions").fetchone()[0])
        user_version = int(con.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return {"count": count, "sum_kopecks": total, "user_version": user_version}


def run_restore_drill(
    db_path: Path | None = None,
    backup_dir: Path | None = None,
    marker_path: Path | None = None,
    now: datetime | None = None,
) -> dict:
    cfg = load_settings()
    live = Path(db_path or cfg.db_path or ROOT / "data" / "spend.db")
    bdir = Path(backup_dir or live.parent / "backup")
    marker = Path(marker_path or bdir / MARKER_NAME)
    marker.parent.mkdir(parents=True, exist_ok=True)

    backup = latest_backup(bdir)
    result: dict = {
        "time": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "file": backup.name if backup else None,
        "status": "failed",
    }
    if backup is None:
        result["reason"] = f"бэкапов нет ({bdir})"
    else:
        try:
            with tempfile.TemporaryDirectory(prefix="restore-drill-") as tmp:
                restored = Path(tmp) / backup.name
                shutil.copy2(backup, restored)
                snap = inspect_db(restored)
            result.update(snap)
            if snap["integrity"] == "ok" and snap["has_transactions"]:
                result["status"] = "ok"
            else:
                result["reason"] = "снимок не прошёл integrity_check/нет таблицы transactions"
        except (sqlite3.Error, OSError) as e:
            result["reason"] = f"не удалось восстановить: {e}"

    live_snap = live_stats(live)
    if live_snap is not None:
        result["live_count"] = live_snap["count"]
        result["live_sum_kopecks"] = live_snap["sum_kopecks"]
        if "count" in result:
            result["count_match"] = result["count"] == live_snap["count"]
            result["sum_match"] = result["sum_kopecks"] == live_snap["sum_kopecks"]

    marker.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Restore-drill последнего бэкапа")
    ap.add_argument("--db", type=Path, default=None, help="путь к живой БД")
    ap.add_argument("--backup-dir", type=Path, default=None, help="папка с spend-*.db")
    args = ap.parse_args()

    result = run_restore_drill(args.db, args.backup_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
