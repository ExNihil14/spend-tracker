from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spendtrack import cli
from spendtrack.doctor import overall_status, run_checks
from spendtrack.main import app
from spendtrack.store import SCHEMA, Store

NOW = "2026-09-16T12:00:00+00:00"


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "data" / "spend.db"
    Store(path).close()
    return path


def _insert(store: Store, **kw) -> None:
    row = {
        "date": "2026-09-10", "description": "ТЕСТ", "amount_kopecks": -100,
        "category": "other", "category_source": "manual", "confidence": 1.0,
        "category_llm": None, "review_status": "approved",
    }
    row.update(kw)
    store.conn.execute(
        "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
        " confidence, category_llm, review_status, created, updated)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (row["date"], row["description"], row["amount_kopecks"], row["category"],
         row["category_source"], row["confidence"], row["category_llm"], row["review_status"],
         NOW, NOW))
    store.conn.commit()


def _check(report: dict, check_id: str) -> dict:
    return next(c for c in report["checks"] if c["id"] == check_id)


def _backup_dir(db_path: Path) -> Path:
    return db_path.parent / "backup"


# ---- ① quick_check ----
def test_quick_check_ok_on_clean_db(db_path):
    report = run_checks(db_path)
    assert report["status"] == "ok"
    assert _check(report, "quick_check")["severity"] == "ok"


def test_quick_check_critical_on_corrupt(db_path):
    store = Store(db_path)
    store.conn.executemany(
        "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
        " confidence, fingerprint, created, updated)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        [("2026-09-01", f"TEST LONG DESCRIPTION PADDING {i}", -100, "other", "manual",
          1.0, f"fp{i}", NOW, NOW) for i in range(300)])
    store.conn.commit()
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # Порча строго корневой страницы transactions (детерминированно, а не фиксированный offset):
    # структурная порча роняет PRAGMA quick_check («malformed») — флейк с TypeError устранён.
    page_size = int(store.conn.execute("PRAGMA page_size").fetchone()[0])
    root = int(store.conn.execute(
        "SELECT rootpage FROM sqlite_master WHERE name='transactions'").fetchone()[0])
    store.close()

    with db_path.open("r+b") as f:  # заливаем корневую страницу целиком (ячейки — в конце страницы)
        f.seek((root - 1) * page_size)
        f.write(b"\xff" * page_size)

    report = run_checks(db_path)
    check = _check(report, "quick_check")
    assert report["status"] == "critical"
    assert check["severity"] == "critical"
    detail = check["detail"].lower()
    # структурная порча либо даёт строки page-ошибок, либо роняет PRAGMA («malformed»)
    assert "page" in detail or "malformed" in detail


def test_quick_check_reports_problem_lines_and_hard_error():
    """Обе ветки quick_check: строки-ошибки со всеми деталями и «PRAGMA упал» → critical."""
    from spendtrack import doctor

    class _FakeConn:
        def __init__(self, outcome):
            self._outcome = outcome

        def execute(self, _sql):
            if isinstance(self._outcome, Exception):
                raise self._outcome
            return self

        def fetchall(self):
            return self._outcome

    rows = [("*** in database main ***\nPage 2: btreeInitPage() returns error code 11",)]
    check = doctor.check_quick_check(_FakeConn(rows))
    assert check["severity"] == "critical"
    assert "Page 2" in check["detail"]

    check = doctor.check_quick_check(_FakeConn(sqlite3.DatabaseError("database disk image is malformed")))
    assert check["severity"] == "critical"
    assert "malformed" in check["detail"]

    assert doctor.check_quick_check(_FakeConn([("ok",)]))["severity"] == "ok"


def test_guarded_turns_unexpected_error_into_critical():
    """Контракт guard: любая упавшая проверка = critical, прогон не падает (TypeError на мусоре)."""
    from spendtrack import doctor

    def boom() -> dict:
        raise TypeError("'NoneType' object is not subscriptable")

    check = doctor._guarded("fingerprint_dupes", boom)
    assert check["severity"] == "critical"
    assert "не удалось выполнить проверку" in check["detail"]


# ---- ② дубли fingerprint ----
def test_fingerprint_dupes_critical(tmp_path):
    path = tmp_path / "dup.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.replace(" UNIQUE", ""))  # снимаем индекс для аномалии
    con.execute("PRAGMA user_version = 4")
    for _ in range(2):
        con.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category,"
            " category_source, confidence, fingerprint, created, updated, review_status)"
            " VALUES('2026-09-01','DUP',-100,'other','manual',1.0,'same',?,?,'approved')",
            (NOW, NOW))
    con.commit()
    con.close()

    report = run_checks(path)
    check = _check(report, "fingerprint_dupes")
    assert report["status"] == "critical"
    assert check["severity"] == "critical" and check["count"] == 1


# ---- ③ user_version ----
def test_schema_version_critical(db_path):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA user_version = 99")
    con.commit()
    con.close()

    report = run_checks(db_path)
    check = _check(report, "schema_version")
    assert report["status"] == "critical"
    assert check["severity"] == "critical" and "99" in check["detail"]


# ---- ④ категории вне таксономии ----
def test_categories_invalid_critical(db_path):
    store = Store(db_path)
    _insert(store, category="марсианская")
    store.close()

    report = run_checks(db_path)
    check = _check(report, "categories_invalid")
    assert report["status"] == "critical"
    assert check["severity"] == "critical" and check["count"] == 1
    assert "марсианская" in check["detail"]
    assert _check(report, "category_llm_invalid")["severity"] == "ok"


def test_category_llm_invalid_warn_and_pending_exempt(db_path):
    store = Store(db_path)
    _insert(store, category_llm="марсианская", category_source="llm")
    _insert(store, category_llm="марсианская", category_source="llm_pending_review",
            review_status="pending")
    _insert(store, category_llm="", category_source="llm")  # пустая строка = нет предложения
    store.close()

    report = run_checks(db_path)
    check = _check(report, "category_llm_invalid")
    assert report["status"] == "warn"
    assert check["severity"] == "warn" and check["count"] == 1  # pending не считается
    assert _check(report, "pending_source")["severity"] == "ok"


def test_refs_invalid_warn(db_path):
    store = Store(db_path)
    store.merchant_cache_set("МЕРЧАНТ", "марсианская")
    store.add_example("ТЕСТ", -100, "марсианская")
    store.set_budget("марсианская", 10_000)
    store.conn.execute("INSERT INTO rules(pattern, category) VALUES('X','марсианская')")
    store.conn.commit()
    store.close()

    report = run_checks(db_path)
    check = _check(report, "refs_invalid")
    assert report["status"] == "warn"
    assert check["severity"] == "warn" and check["count"] == 4
    assert "rules=1" in check["detail"] and "budgets=1" in check["detail"]


def test_refs_invalid_null_budget_category(db_path):
    """budgets.category — TEXT PRIMARY KEY: SQLite допускает NULL (в отличие от NOT NULL-колонок)."""
    store = Store(db_path)
    store.conn.execute(
        "INSERT INTO budgets(category, amount_kopecks, updated) VALUES(NULL, 100, ?)", (NOW,))
    store.conn.commit()
    store.close()

    check = _check(run_checks(db_path), "refs_invalid")
    assert check["severity"] == "warn" and check["count"] == 1 and "budgets=1" in check["detail"]


# ---- ⑤ pending с чужим источником ----
def test_pending_source_warn(db_path):
    store = Store(db_path)
    _insert(store, review_status="pending", category_source="rule")
    store.close()

    report = run_checks(db_path)
    check = _check(report, "pending_source")
    assert report["status"] == "warn"
    assert check["severity"] == "warn" and check["count"] == 1


# ---- ⑥ пустые партии импорта ----
def test_empty_batches_info(db_path):
    store = Store(db_path)
    batch = store.add_batch("sber.csv", "sha", 0)
    store.close()

    report = run_checks(db_path)
    check = _check(report, "empty_batches")
    assert report["status"] == "ok"  # info не эскалирует
    assert check["severity"] == "info" and check["count"] == 1
    assert batch in check["detail"]

    store = Store(db_path)
    store.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                          category="other", category_source="import", import_batch=batch)
    store.close()
    assert _check(run_checks(db_path), "empty_batches")["severity"] == "ok"


# ---- ⑦ бэкапы ----
def test_backup_missing_info(db_path):
    check = _check(run_checks(db_path), "backup")
    assert check["severity"] == "info" and check["count"] == 0
    assert str(_backup_dir(db_path)) in check["detail"]


def test_backup_fresh_ok(db_path):
    _backup_dir(db_path).mkdir(parents=True)
    Store(_backup_dir(db_path) / "spend-20260916-000000.db").close()

    check = _check(run_checks(db_path), "backup")
    assert check["severity"] == "ok" and check["count"] == 1


def test_backup_stale_warn(db_path):
    _backup_dir(db_path).mkdir(parents=True)
    snap = _backup_dir(db_path) / "spend-20260910-000000.db"
    Store(snap).close()
    old = time.time() - 72 * 3600
    os.utime(snap, (old, old))

    report = run_checks(db_path)
    check = _check(report, "backup")
    assert report["status"] == "warn"
    assert check["severity"] == "warn" and "48ч" in check["detail"]


def test_backup_empty_dir_info(db_path):
    """Папка есть, но копий нет — тот же info, что и при отсутствии папки."""
    _backup_dir(db_path).mkdir(parents=True)

    check = _check(run_checks(db_path), "backup")
    assert check["severity"] == "info" and check["count"] == 0 and "бэкапов нет" in check["detail"]


def test_backup_zero_byte_snapshot_critical(db_path):
    """Файл 0 байт прошёл бы quick_check как пустая БД — ловим отсутствие таблицы transactions."""
    _backup_dir(db_path).mkdir(parents=True)
    (_backup_dir(db_path) / "spend-20260916-130000.db").write_bytes(b"")

    report = run_checks(db_path)
    check = _check(report, "backup")
    assert report["status"] == "critical"
    assert check["severity"] == "critical" and "transactions" in check["detail"]


def test_guarded_oserror_becomes_critical(db_path, monkeypatch):
    """Нет доступа к файлам бэкапа — doctor не падает, чек становится critical."""
    def _boom(path):
        raise PermissionError("нет доступа")

    monkeypatch.setattr("spendtrack.doctor.check_backup", _boom)
    report = run_checks(db_path)
    check = _check(report, "backup")
    assert report["status"] == "critical" and check["severity"] == "critical"
    assert "нет доступа" in check["detail"]


def test_backup_corrupt_critical(db_path):
    _backup_dir(db_path).mkdir(parents=True)
    (_backup_dir(db_path) / "spend-20260916-120000.db").write_bytes(b"not a database")

    report = run_checks(db_path)
    check = _check(report, "backup")
    assert report["status"] == "critical"
    assert check["severity"] == "critical" and check["count"] == 1


def test_backup_path_with_space_ok(tmp_path):
    """ro-URI с пробелами в пути (%20) должен открываться: as_uri() + SQLite URI-декодирование."""
    db = tmp_path / "with space" / "spend.db"
    Store(db).close()
    (tmp_path / "with space" / "backup").mkdir()
    Store(tmp_path / "with space" / "backup" / "spend-20260916-000000.db").close()

    assert _check(run_checks(db), "backup")["severity"] == "ok"


# ---- фолбэки и приоритет severity ----
def test_db_open_critical(tmp_path):
    path = tmp_path / "broken.db"
    path.write_bytes(b"\x00\xff not a sqlite file " * 8)

    report = run_checks(path)
    check = _check(report, "db_open")
    assert report["status"] == "critical" and check["severity"] == "critical"


def test_taxonomy_config_critical(db_path, monkeypatch):
    def _boom():
        raise ValueError("битый TOML")

    monkeypatch.setattr("spendtrack.doctor.load_taxonomy", _boom)
    report = run_checks(db_path)
    check = _check(report, "taxonomy_config")
    assert report["status"] == "critical" and check["severity"] == "critical"


def test_overall_status_precedence():
    assert overall_status([{"severity": "ok"}, {"severity": "info"}]) == "ok"
    assert overall_status([{"severity": "ok"}, {"severity": "warn"}, {"severity": "info"}]) == "warn"
    assert overall_status([{"severity": "warn"}, {"severity": "critical"}]) == "critical"


# ---- API ----
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "api.db"))
    return TestClient(app)


def test_api_health_data_ok(client):
    r = client.get("/health/data")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert {c["id"] for c in body["checks"]} >= {"quick_check", "fingerprint_dupes", "backup"}
    assert client.get("/health").json() == {"status": "ok", "transactions": 0}  # liveness не тронут


def test_api_health_data_503_on_critical(tmp_path, monkeypatch):
    path = tmp_path / "api.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(path))
    Store(path).close()
    con = sqlite3.connect(path)
    con.execute("PRAGMA user_version = 99")
    con.commit()
    con.close()

    r = TestClient(app).get("/health/data")
    assert r.status_code == 503
    assert r.json()["status"] == "critical"


# ---- CLI ----
def test_cli_doctor_json_ok(db_path, monkeypatch, capsys):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db_path))
    rc = cli.main(["doctor", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert report["status"] == "ok"
    assert len(report["checks"]) == 9


def test_cli_doctor_critical_exit1(db_path, monkeypatch, capsys):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA user_version = 99")
    con.commit()
    con.close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db_path))

    assert cli.main(["doctor"]) == 1
    human = capsys.readouterr().out
    assert human.startswith("doctor: CRITICAL")
    assert "schema_version" in human

    assert cli.main(["doctor", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "critical"
