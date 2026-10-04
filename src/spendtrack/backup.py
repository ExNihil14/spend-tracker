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
import os
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.checksum import sha256_file
from spendtrack.config import resolve_db_path
from spendtrack.console import utf8_stdout

OFFSITE_MARKER = "last_offsite_copy.json"
DEFAULT_KEEP = 14


def default_db_path() -> Path:
    """Путь БД как у остальных команд: единая точка `config.resolve_db_path()` (S3/C2, 03.10)."""
    return resolve_db_path()


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
        "forced": bool(force),  # честность маркера: doctor покажет warn «на том же томе» (ревью S5)
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def backup_dir_for(db_path: Path) -> Path:
    """Папка локальных снимков КОНКРЕТНОЙ БД: `<parent>/backup/<stem>` (Astra 01.10, C1).

    Разные БД в одной папке (`spend.db` / `demo.db`) больше не делят снимки, ротацию и маркеры:
    раньше ротация одной БД могла удалить единственную копию другой.
    """
    db_path = Path(db_path)
    return db_path.parent / "backup" / db_path.stem


def legacy_backup_dir(db_path: Path) -> Path:
    """Плоская раскладка до 01.10 (`<parent>/backup`) — только чтение (совместимость)."""
    return Path(db_path).parent / "backup"


def find_snapshots(db_path: Path) -> tuple[Path, list[Path]]:
    """(папка, снимки): приоритет — новая раскладка; пусто — legacy-плоская (чтение старых копий)."""
    new_dir = backup_dir_for(db_path)
    files = sorted(new_dir.glob("spend-*.db"), key=lambda p: (p.stat().st_mtime, p.name))
    if files:
        return new_dir, files
    legacy = legacy_backup_dir(db_path)
    files = sorted(legacy.glob("spend-*.db"), key=lambda p: (p.stat().st_mtime, p.name))
    return (legacy, files) if files else (new_dir, [])


def make_snapshot(db_path: Path) -> Path:
    """VACUUM INTO-снимок в папку своей БД; два снимка в одну секунду не перезаписываются."""
    backup_dir = backup_dir_for(db_path)
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
    except BaseException:
        # Частичный файл не должен стать «самым свежим бэкапом» (ревью install_ops, S6: disk full);
        # сбой unlink (Windows: файл занят) не должен маскировать исходную ошибку (ревью Dash 4.6).
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
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


LOCK_NAME = ".backup.lock"
LOCK_STALE_S = 2 * 3600  # аварийный остаток lock старше 2 ч снимается автоматически


def _acquire_backup_lock(backup_dir: Path) -> Path | None:
    """Эксклюзивный lock операции бэкапа (Astra 01.10, S2).

    Возвращает путь lock-файла; None — если бэкап уже выполняется. Зависший lock
    (файл старше 2 ч — процесс, вероятно, умер) снимается автоматически.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    lock = backup_dir / LOCK_NAME
    if lock.exists():
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            age = 0
        if age > LOCK_STALE_S:
            lock.unlink(missing_ok=True)  # аварийный остаток: владелец давно не работает
        else:
            return None
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    return lock


LAZY_BACKUP_HOURS = 168  # C3: неделя — ленивый бэкап на старте `serve` (задача Планировщика — отдельно)


def lazy_backup_if_stale(db_path: Path | str | None = None, *, now: float | None = None) -> dict:
    """C3 (03.10): снимок на старте `serve`, если свежего нет или он старше порога.

    Порог: SPENDTRACK_LAZY_BACKUP_HOURS (0 — выключить; дефолт 168 ч). Никогда не бросает:
    сервер обязан подняться в любом случае (любой сбой → {"status": "failed"}).
    Возвращает {status}: off/skipped/fresh/locked/created/failed.
    """
    try:
        return _lazy_backup_impl(db_path, now=now)
    except Exception as e:  # noqa: BLE001 — контракт «никогда не бросает» (ревью wave5, ops_spend №2)
        return {"status": "failed", "reason": f"{type(e).__name__}: {e}"}


def _lazy_backup_impl(db_path: Path | str | None, *, now: float | None) -> dict:
    try:
        hours = float(os.environ.get("SPENDTRACK_LAZY_BACKUP_HOURS") or LAZY_BACKUP_HOURS)
    except ValueError:
        hours = float(LAZY_BACKUP_HOURS)
    if hours <= 0:
        return {"status": "off"}
    db = Path(db_path).expanduser() if db_path else default_db_path()
    if not db.exists():
        return {"status": "skipped", "reason": f"БД не найдена: {db}"}
    _bdir, files = find_snapshots(db)
    ref = time.time() if now is None else now
    if files:
        newest = max(files, key=lambda p: (p.stat().st_mtime, p.name))
        try:
            age_h = (ref - newest.stat().st_mtime) / 3600
        except OSError:
            age_h = None
        if age_h is not None and age_h <= hours:
            return {"status": "fresh", "file": newest.name, "age_h": round(age_h, 1)}
    lock = _acquire_backup_lock(backup_dir_for(db))
    if lock is None:
        return {"status": "locked"}
    try:
        snap = make_snapshot(db)
        rotate(backup_dir_for(db), DEFAULT_KEEP, current=snap)
        return {"status": "created", "file": snap.name}
    except (sqlite3.Error, OSError, RuntimeError) as e:
        return {"status": "failed", "reason": str(e)}
    finally:
        lock.unlink(missing_ok=True)


def run_backup(
    db_path: Path | str | None = None,
    *,
    keep: int = DEFAULT_KEEP,
    copy_to: str | Path | None = None,
    force: bool = False,
) -> int:
    """Локальный снимок + ротация [+ внешняя копия]. 0 — успех, 1 — понятная ошибка в stderr.

    Весь участок «снимок → внешняя копия → ротация» защищён эксклюзивным lock-файлом:
    параллельный запуск для той же БД отклоняется (Astra 01.10, S2), а не удаляет снимки друг друга.
    """
    utf8_stdout()
    if keep < 1:
        print(f"--keep должен быть >= 1 (получено {keep}): единственный снимок не удаляем",
              file=sys.stderr, flush=True)
        return 1
    db = Path(db_path).expanduser() if db_path else default_db_path()
    if not db.exists():
        print(f"БД не найдена: {db}", file=sys.stderr, flush=True)
        return 1
    lock = _acquire_backup_lock(backup_dir_for(db))
    if lock is None:
        print(f"бэкап уже выполняется (lock: {backup_dir_for(db) / LOCK_NAME}) — повторный запуск отклонён; "
              "если процесс завершился аварийно, удалите lock-файл вручную", file=sys.stderr, flush=True)
        return 1
    try:
        return _run_backup_locked(db, keep=keep, copy_to=copy_to, force=force)
    finally:
        lock.unlink(missing_ok=True)


def _run_backup_locked(
    db: Path,
    *,
    keep: int,
    copy_to: str | Path | None,
    force: bool,
) -> int:
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
    utf8_stdout()
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
