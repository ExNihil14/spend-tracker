"""Бэкап БД через VACUUM INTO (консистентная копия при живом сервере) + внешняя копия.

CLI:  spendtrack backup [--keep N] [--copy-to ПАПКА] [--force]
Dev:  python -m spendtrack.backup … / scripts/backup.py (тонкая обёртка)

Создаёт backup/spend-YYYYMMDD-HHMMSS.db (SQLite), ротацию по дате.
Работает при работающем сервере: VACUUM INTO делает снимок read-transaction.

--copy-to дополнительно копирует свежий снимок наружу (USB/другой диск/папка облака):
отказ, если копия на том же томе, что и БД (исключение — --force); проверка sha256 после
копирования и маркер backup/last_offsite_copy.json (его читает doctor-чек offsite_backup).
Ротация --keep (>= 1) касается только локальной папки и идёт ПОСЛЕ offsite-копии; свежий снимок
не удаляется никогда, порядок файлов — по mtime (тот же критерий, что у doctor).
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
from spendtrack.config import load_settings, resolve_data_dir
from spendtrack.console import utf8_stdout

OFFSITE_MARKER = "last_offsite_copy.json"
DEFAULT_KEEP = 14


def default_db_path() -> Path:
    """Путь БД как у остальных команд: SPENDTRACK_DB_PATH → data/ репо → user-data."""
    cfg = load_settings()
    return Path(cfg.db_path).expanduser() if cfg.db_path else resolve_data_dir() / "spend.db"


def same_device(a: Path, b: Path) -> bool:
    """Один и тот же том/диск (на Windows st_dev — серийный номер тома).

    Сетевые пути (SMB/NFS) могут давать ложное срабатывание — тогда осознанно `--force`.
    """
    return Path(a).stat().st_dev == Path(b).stat().st_dev


def copy_offsite(snapshot: Path, target_dir: Path, *, force: bool = False) -> Path:
    """Копирует снимок в target_dir (создаёт папку), сверяет sha256, пишет маркер.

    Ошибки политики/доступа — ValueError (run_backup печатает и возвращает 1).
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


def make_snapshot(db_path: Path) -> Path:
    """VACUUM INTO-снимок в соседнюю папку backup/; два снимка в одну секунду не перезаписываются."""
    backup_dir = Path(db_path).parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"spend-{stamp}.db"
    n = 1
    while target.exists():
        target = backup_dir / f"spend-{stamp}-{n}.db"
        n += 1
    con = sqlite3.connect(db_path, timeout=30)
    try:
        quoted = str(target).replace("'", "''")
        con.execute(f"VACUUM INTO '{quoted}'")
    finally:
        con.close()
    return target


def rotate(backup_dir: Path, keep: int, *, current: Path | None = None) -> tuple[Path, ...]:
    """Удаляет старые локальные снимки сверх keep; порядок — по mtime (как doctor), не по имени.

    `current` (свежий снимок) не удаляется никогда и занимает один из слотов keep: при keep=1
    локально остаётся ровно он (внешние копии — вне этой папки). Имена в UTC + суффикс дубля
    секунды ломали сортировку по имени; mtime — единый критерий с doctor.check_backup.
    """
    files = sorted(Path(backup_dir).glob("spend-*.db"),
                   key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    current = Path(current) if current is not None else None
    if current is not None and current in files:
        files.remove(current)
        files.insert(0, current)
    removed: list[Path] = []
    for old in files[keep:]:
        old.unlink(missing_ok=True)
        removed.append(old)
    return tuple(removed)


def run_backup(
    db_path: Path | str | None = None,
    *,
    keep: int = DEFAULT_KEEP,
    copy_to: str | Path | None = None,
    force: bool = False,
) -> int:
    """Локальный снимок + ротация [+ внешняя копия]. 0 — успех, 1 — понятная ошибка в stderr."""
    utf8_stdout()
    if keep < 1:
        print(f"--keep должен быть >= 1 (получено {keep}): единственный снимок не удаляем",
              file=sys.stderr, flush=True)
        return 1
    db = Path(db_path).expanduser() if db_path else default_db_path()
    if not db.exists():
        print(f"БД не найдена: {db}", file=sys.stderr, flush=True)
        return 1
    try:
        target = make_snapshot(db)
    except (sqlite3.Error, OSError) as e:
        print(f"ошибка бэкапа: {e}", file=sys.stderr, flush=True)
        return 1
    print(f"OK: {target} ({target.stat().st_size} байт)", flush=True)

    # Offsite-копия — ДО ротации: при её отказе старые снимки остаются нетронутыми,
    # а «--keep 0» больше не может уничтожить только что созданный снимок до копирования.
    if copy_to:
        try:
            dest = copy_offsite(target, Path(copy_to), force=force)
        except (ValueError, OSError) as e:
            print(f"ошибка внешней копии: {e}", file=sys.stderr, flush=True)
            return 1
        digest = sha256_file(dest)
        print(f"OK (вне диска): {dest} ({dest.stat().st_size} байт, sha256 {digest[:12]}…)",
              flush=True)

    # Ротация после снимка и копии; OSError (Windows: файл занят антивирусом/индексатором) —
    # предупреждение, а не трейсбек: бэкап уже создан и важнее удаления старых.
    try:
        for old in rotate(target.parent, keep, current=target):
            print(f"удалён старый: {old}", flush=True)
    except OSError as e:
        print(f"предупреждение: ротация не завершена ({e})", file=sys.stderr, flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Бэкап БД (VACUUM INTO) + внешняя копия")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="сколько локальных копий хранить")
    ap.add_argument("--copy-to", default=None, metavar="ПАПКА",
                    help="копия вне диска БД (USB/облачная папка)")
    ap.add_argument("--force", action="store_true",
                    help="разрешить копию на тот же диск (осознанное исключение)")
    args = ap.parse_args(argv)
    return run_backup(keep=args.keep, copy_to=args.copy_to, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
