"""Offsite-бэкап (POLISH_PLAN #12): `scripts/backup.py --copy-to` — загрузка скрипта, guard «тот же диск», sha256, маркер."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from spendtrack.checksum import sha256_file
from spendtrack.store import Store

ROOT = Path(__file__).resolve().parents[1]


def _backup_module():
    spec = importlib.util.spec_from_file_location("backup_script", ROOT / "scripts" / "backup.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def backup_mod():
    return _backup_module()


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


def test_local_backup_created(backup_mod, db_path, capsys):
    assert backup_mod.main([]) == 0
    assert "OK:" in capsys.readouterr().out
    assert len(list(_backup_dir(db_path).glob("spend-*.db"))) == 1


def test_same_device_same_volume(backup_mod, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    assert backup_mod.same_device(tmp_path, sub)


def test_copy_offsite_ok(backup_mod, db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup_mod, "same_device", lambda a, b: False)
    usb = tmp_path / "usb" / "spendtrack-backup"  # папки ещё нет — создаётся
    assert backup_mod.main(["--copy-to", str(usb)]) == 0
    assert "вне диска" in capsys.readouterr().out

    files = list(usb.glob("spend-*.db"))
    assert len(files) == 1
    marker = json.loads((_backup_dir(db_path) / "last_offsite_copy.json").read_text("utf-8"))
    assert Path(marker["dest"]) == files[0]
    assert marker["sha256"] == sha256_file(files[0])
    assert marker["size"] == files[0].stat().st_size


def test_copy_same_disk_refused(backup_mod, db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup_mod, "same_device", lambda a, b: True)
    usb = tmp_path / "usb"
    assert backup_mod.main(["--copy-to", str(usb)]) == 1
    assert "тот же диск" in capsys.readouterr().err
    assert not list(usb.glob("spend-*.db"))
    assert not (_backup_dir(db_path) / "last_offsite_copy.json").exists()
    assert list(_backup_dir(db_path).glob("spend-*.db"))  # локальный бэкап всё равно создан


def test_copy_same_disk_force(backup_mod, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "same_device", lambda a, b: True)
    usb = tmp_path / "usb"
    assert backup_mod.main(["--copy-to", str(usb), "--force"]) == 0
    assert len(list(usb.glob("spend-*.db"))) == 1


def test_copy_dir_not_creatable(backup_mod, db_path, tmp_path, capsys):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    assert backup_mod.main(["--copy-to", str(blocker / "sub")]) == 1
    assert "папка недоступна" in capsys.readouterr().err


def test_copy_to_file_path_rejected(backup_mod, db_path, tmp_path, capsys):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    assert backup_mod.main(["--copy-to", str(blocker)]) == 1
    assert "не папка" in capsys.readouterr().err


def test_keep_rotation_does_not_touch_offsite_dir(backup_mod, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "same_device", lambda a, b: False)
    usb = tmp_path / "usb"
    usb.mkdir()
    (usb / "spend-19990101-000000.db").write_bytes(b"old")
    for h in range(3):  # 3 локальных копии «прошлых» запусков
        (db_path.parent / "backup").mkdir(parents=True, exist_ok=True)
        (db_path.parent / "backup" / f"spend-2026090{h + 1}-000000.db").write_bytes(b"x")

    assert backup_mod.main(["--keep", "1", "--copy-to", str(usb)]) == 0
    local = sorted((db_path.parent / "backup").glob("spend-*.db"))
    assert len(local) == 1, [p.name for p in local]
    external = sorted(p.name for p in usb.glob("spend-*.db"))
    assert len(external) == 2, external  # старый внешний + свежая копия, ротация их не трогает
    assert "spend-19990101-000000.db" in external


def test_copy_sha_mismatch_removes_copy(backup_mod, db_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backup_mod, "same_device", lambda a, b: False)
    calls = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(backup_mod, "sha256_file", lambda p: next(calls))
    usb = tmp_path / "usb"
    assert backup_mod.main(["--copy-to", str(usb)]) == 1
    assert "sha256" in capsys.readouterr().err
    assert not list(usb.glob("spend-*.db"))  # битую копию не оставляем
    assert not (_backup_dir(db_path) / "last_offsite_copy.json").exists()


def test_missing_db(backup_mod, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "nope.db"))
    assert backup_mod.main([]) == 1
    assert "не найдена" in capsys.readouterr().out
