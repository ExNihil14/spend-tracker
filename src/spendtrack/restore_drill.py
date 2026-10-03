"""Restore-drill: проверка, что свежий бэкап реально восстанавливается и читается.

Берёт последний `spend-*.db` (бэкапы — `VACUUM INTO`-снимки, консистентные одиночные файлы
без `-wal`/`-shm`; раскладка — папка своей БД + legacy-fallback `find_snapshots`), копирует
во временную папку, прогоняет `PRAGMA integrity_check`, проверяет таблицу `transactions`
и `user_version`, сверяет COUNT/SUM(amount_kopecks) с живой БД информативно (расхождение
из-за новых транзакций — не ошибка) и пишет маркер `last_restore_drill.json` для doctor-чека.

C2 (тикет 03.10): модуль перенесён в пакет; путь к живой БД — `config.resolve_db_path()`
(без legacy ROOT и cwd-зависимости). `scripts/restore_drill.py` — тонкий шим для совместимости.

Использование:
    uv run python -m spendtrack.restore_drill
    spendtrack backup --drill   # снимок + проверка восстановимости
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.backup import find_snapshots
from spendtrack.config import resolve_db_path
from spendtrack.store import SCHEMA_VERSION, Store

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
    live = Path(db_path) if db_path is not None else resolve_db_path()
    if backup_dir is not None:
        bdir = Path(backup_dir)
    else:
        # Astra 01.10 (S8): раскладка снимков — как у backup/doctor (папка своей БД + legacy-fallback)
        bdir, _files = find_snapshots(live)
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
                if snap["user_version"] > SCHEMA_VERSION:
                    # S9 (Astra 01.10): снимок новее приложения не «восстановим» — явный отказ
                    result["reason"] = (f"снимок новее приложения (schema v{snap['user_version']}"
                                        f" > v{SCHEMA_VERSION}) — несовместим")
                else:
                    # S9: открытие штатным Store на КОПИИ (миграция проверяется, исходный снимок не трогаем)
                    probe = Store(db_path=restored)
                    probe.close()
                    if snap["integrity"] == "ok" and snap["has_transactions"]:
                        result["status"] = "ok"
                    else:
                        result["reason"] = "снимок не прошёл integrity_check/нет таблицы transactions"
        except (sqlite3.Error, OSError, RuntimeError) as e:
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
