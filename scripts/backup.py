"""Бэкап БД через VACUUM INTO (консистентная копия при живом сервере) + offsite-копия.

Использование:
    uv run python -m scripts.backup
    uv run python -m scripts.backup --keep 14
    uv run python -m scripts.backup --copy-to E:\\spendtrack-backup

Создаёт backup/spend-YYYYMMDD-HHMMSS.db (SQLite), ротацию по дате.
Работает при работающем сервере: VACUUM INTO делает снимок read-transaction.

--copy-to дополнительно копирует свежий снимок наружу (USB/другой диск/папка облака):
скрипт отказывается класть копию на тот же том, что и БД (исключение — --force),
проверяет sha256 после копирования и пишет маркер backup/last_offsite_copy.json
(его читает doctor-чек offsite_backup). Ротация --keep касается только локальной папки.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.checksum import sha256_file
from spendtrack.config import ROOT, load_settings

OFFSITE_MARKER = "last_offsite_copy.json"


def same_device(a: Path, b: Path) -> bool:
    """Один и тот же том/диск (на Windows st_dev — серийный номер тома).

    Сетевые пути (SMB/NFS) могут давать ложное срабатывание — тогда осознанно `--force`.
    """
    return Path(a).stat().st_dev == Path(b).stat().st_dev


def copy_offsite(snapshot: Path, target_dir: Path, *, force: bool = False) -> Path:
    """Копирует снимок в target_dir (создаёт папку), сверяет sha256, пишет маркер.

    Ошибки политики/доступа — ValueError (main печатает и возвращает 1).
    """
    snapshot = Path(snapshot)
    target_dir = Path(target_dir).expanduser()
    if target_dir.exists() and not target_dir.is_dir():
        raise ValueError(f"путь существует и это не папка: {target_dir}")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ValueError(f"папка недоступна: {target_dir} ({e})") from e
    if not force and same_device(snapshot, target_dir):
        raise ValueError(
            f"копия на тот же диск, что и БД ({target_dir}) — offsite-бэкап теряет смысл; "
            "подключите USB/другой диск или укажите --force"
        )
    dest = target_dir / snapshot.name
    shutil.copy2(snapshot, dest)
    digest = sha256_file(snapshot)
    if sha256_file(dest) != digest:
        dest.unlink(missing_ok=True)
        raise ValueError(f"sha256 не совпала после копирования: {dest}")
    marker = snapshot.parent / OFFSITE_MARKER
    marker.write_text(json.dumps({
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(snapshot),
        "dest": str(dest),
        "sha256": digest,
        "size": dest.stat().st_size,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def _utf8_stdout() -> None:
    """Пайп/Git Bash на RU-Windows отдаёт cp1251 — кириллица в отчёте мазалась (как в CLI)."""
    out = sys.stdout
    enc = (getattr(out, "encoding", "") or "").lower()
    if enc not in ("utf-8", "utf8") and hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="Бэкап БД (VACUUM INTO) + внешняя копия")
    ap.add_argument("--keep", type=int, default=14, help="сколько локальных копий хранить")
    ap.add_argument("--copy-to", default=None, metavar="ПАПКА",
                    help="копия вне диска БД (USB/облачная папка)")
    ap.add_argument("--force", action="store_true",
                    help="разрешить копию на тот же диск (осознанное исключение)")
    args = ap.parse_args(argv)

    cfg = load_settings()
    db_path = Path(cfg.db_path).resolve() if cfg.db_path else ROOT / "data" / "spend.db"
    if not db_path.exists():
        print(f"БД не найдена: {db_path}", flush=True)
        return 1

    backup_dir = db_path.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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

    if args.copy_to:
        try:
            dest = copy_offsite(target, Path(args.copy_to), force=args.force)
        except (ValueError, OSError) as e:
            print(f"ошибка внешней копии: {e}", file=sys.stderr, flush=True)
            return 1
        digest = sha256_file(dest)
        print(f"OK (вне диска): {dest} ({dest.stat().st_size} байт, sha256 {digest[:12]}…)",
              flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
