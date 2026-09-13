"""Бэкап БД через VACUUM INTO (консистентная копия при живом сервере).

Использование:
    uv run python -m scripts.backup
    uv run python -m scripts.backup --keep 14

Создаёт backup/spend-YYYYMMDD.db (SQLite), ротацию по дате.
Работает при работающем сервере: VACUUM INTO делает снимок read-transaction.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.config import ROOT, load_settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=14, help="сколько копий хранить")
    args = ap.parse_args()

    cfg = load_settings()
    db_path = Path(cfg.db_path).resolve() if cfg.db_path else ROOT / "data" / "spend.db"
    if not db_path.exists():
        print(f"БД не найдена: {db_path}", flush=True)
        return 1

    backup_dir = db_path.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    target = backup_dir / f"spend-{stamp}.db"

    con = sqlite3.connect(db_path, timeout=30)
    try:
        quoted = str(target).replace("'", "''")
        con.execute(f"VACUUM INTO '{quoted}'")
    finally:
        con.close()
    print(f"OK: {target} ({target.stat().st_size} байт)", flush=True)

    keep = sorted(backup_dir.glob("spend-*.db"), reverse=True)
    for old in keep[args.keep:]:
        old.unlink(missing_ok=True)
        print(f"удалён старый: {old}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    main()