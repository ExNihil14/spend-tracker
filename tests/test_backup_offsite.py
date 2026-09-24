"""Бэкап (POLISH_PLAN #12, K2): `spendtrack backup` — снимок, ротация, offsite-копия, маркер.

Логика — `spendtrack.backup` (пользовательский CLI + dev-обёртка `scripts/backup.py`).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from spendtrack import backup
from spendtrack.checksum import sha256_file
from spendtrack.store import Store


@pytest.fixture()
def db_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "data" / "spend.db"
    store = Store(path)
    store.add_transaction(date="2026-09-01", description="ТЕСТ", amount_kopecks=-100,
                          category="other", category_source="manual")
    store.close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(path))
    return path


def _backup_dir(db_path: Path) -> Path:
    return db_path.parent / "backup"


def test_local_backup_created(db_path, capsys):
    assert backup.main([]) == 0
    assert "OK:" in capsys.readouterr().out
    assert len(list(_backup_dir(db_path).glob("spend-*.db"))) == 1


def test_same_device_same_volume(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    assert backup.same_device(tmp_path, sub)


def test_copy_offsite_ok(db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup, "same_device", lambda a, b: False)
    usb = tmp_path / "usb" / "spendtrack-backup"  # папки ещё нет — создаётся
    assert backup.main(["--copy-to", str(usb)]) == 0
    assert "вне диска" in capsys.readouterr().out

    files = list(usb.glob("spend-*.db"))
    assert len(files) == 1
    marker = json.loads((_backup_dir(db_path) / "last_offsite_copy.json").read_text("utf-8"))
    assert Path(marker["dest"]) == files[0]
    assert marker["sha256"] == sha256_file(files[0])
    assert marker["size"] == files[0].stat().st_size


def test_copy_same_disk_refused(db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup, "same_device", lambda a, b: True)
    usb = tmp_path / "usb"
    assert backup.main(["--copy-to", str(usb)]) == 1
    assert "тот же диск" in capsys.readouterr().err
    assert not list(usb.glob("spend-*.db"))
    assert not (_backup_dir(db_path) / "last_offsite_copy.json").exists()
    assert list(_backup_dir(db_path).glob("spend-*.db"))  # локальный бэкап всё равно создан


def test_copy_same_disk_force(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "same_device", lambda a, b: True)
    usb = tmp_path / "usb"
    assert backup.main(["--copy-to", str(usb), "--force"]) == 0
    assert len(list(usb.glob("spend-*.db"))) == 1


def test_copy_dir_not_creatable(db_path, tmp_path, capsys):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    assert backup.main(["--copy-to", str(blocker / "sub")]) == 1
    assert "папка недоступна" in capsys.readouterr().err


def test_copy_to_file_path_rejected(db_path, tmp_path, capsys):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    assert backup.main(["--copy-to", str(blocker)]) == 1
    assert "не папка" in capsys.readouterr().err


def test_keep_rotation_does_not_touch_offsite_dir(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "same_device", lambda a, b: False)
    usb = tmp_path / "usb"
    usb.mkdir()
    (usb / "spend-19990101-000000.db").write_bytes(b"old")
    for h in range(3):  # 3 локальных копии «прошлых» запусков
        (db_path.parent / "backup").mkdir(parents=True, exist_ok=True)
        (db_path.parent / "backup" / f"spend-2026090{h + 1}-000000.db").write_bytes(b"x")

    assert backup.main(["--keep", "1", "--copy-to", str(usb)]) == 0
    local = sorted((db_path.parent / "backup").glob("spend-*.db"))
    assert len(local) == 1, [p.name for p in local]
    external = sorted(p.name for p in usb.glob("spend-*.db"))
    assert len(external) == 2, external  # старый внешний + свежая копия, ротация их не трогает
    assert "spend-19990101-000000.db" in external


def test_copy_sha_mismatch_removes_copy(db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup, "same_device", lambda a, b: False)
    calls = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(backup, "sha256_file", lambda p: next(calls))
    usb = tmp_path / "usb"
    assert backup.main(["--copy-to", str(usb)]) == 1
    assert "sha256" in capsys.readouterr().err
    assert not list(usb.glob("spend-*.db"))  # битую копию не оставляем
    assert not (_backup_dir(db_path) / "last_offsite_copy.json").exists()


def test_missing_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "nope.db"))
    assert backup.main([]) == 1
    assert "не найдена" in capsys.readouterr().err


def test_two_snapshots_in_same_second_do_not_overwrite(db_path, monkeypatch):
    """Снимок за ту же секунду получает суффикс, а не перезапись (ручной двойной запуск)."""
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 24, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(backup, "datetime", _FixedDatetime)
    first = backup.make_snapshot(db_path)
    second = backup.make_snapshot(db_path)
    assert first != second
    assert {p.name for p in _backup_dir(db_path).glob("spend-*.db")} == {
        "spend-20260924-120000.db", "spend-20260924-120000-1.db"}


def test_run_backup_reports_unreadable_db(tmp_path, capsys):
    """Мусорный файл на месте БД — понятная ошибка, а не трейсбек."""
    junk = tmp_path / "spend.db"
    junk.write_text("это не база", encoding="utf-8")
    assert backup.run_backup(junk) == 1
    assert "ошибка бэкапа" in capsys.readouterr().err
