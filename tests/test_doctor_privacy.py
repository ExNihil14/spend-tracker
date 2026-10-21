"""Приватность вывода doctor: по умолчанию — только коды/счётчики, без описаний и мерчантов.

Причина (privacy pack 21.10): `doctor` печатает `detail` в терминал и в `--json`, а часть проверок
вставляла туда сырые строки операций (`ЛЕНТА×2`, список мёртвых мерчантов). Для скриншотов в issue
и для `--share` это лишний egress. Контракт: библиотечный `run_checks()` по умолчанию сохраняет
прежнее поведение (details=True — на нём стоят существующие тесты), а **CLI** по умолчанию
показывает минимум; полный текст — только по явному `--details`.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from spendtrack import cli, doctor
from spendtrack.doctor import run_checks
from spendtrack.main import app
from spendtrack.store import Store


def _db_with_sensitive_rows(db_path) -> None:
    store = Store(db_path)
    store.add_example("ЛЕНТА", -100, "groceries")
    store.add_example("ЛЕНТА", -100, "groceries")          # дубль → examples_dupes
    store.add_transaction(date="2026-09-10", description="ТЕСТ", amount_kopecks=-100,
                          category="other", category_source="manual", merchant="ЛЕНТА")
    store.merchant_cache_set("ЛЕНТА", "groceries")          # живой
    store.merchant_cache_set("СТАРЫЙ_МЕРЧАНТ", "groceries")  # мёртвый → merchant_cache_dead
    store.close()


def test_run_checks_details_false_hides_raw_text(tmp_path):
    db_path = tmp_path / "spend.db"
    _db_with_sensitive_rows(db_path)
    report = run_checks(db_path, details=False)
    checks = {c["id"]: c for c in report["checks"]}

    assert checks["examples_dupes"]["count"] == 1
    assert "ЛЕНТА" not in checks["examples_dupes"]["detail"]

    assert checks["merchant_cache_dead"]["count"] == 1
    assert "СТАРЫЙ_МЕРЧАНТ" not in checks["merchant_cache_dead"]["detail"]


def test_run_checks_details_true_keeps_raw_text(tmp_path):
    """Обратная совместимость библиотечного вызова: details=True (по умолчанию) — как раньше."""
    db_path = tmp_path / "spend.db"
    _db_with_sensitive_rows(db_path)
    checks = {c["id"]: c for c in run_checks(db_path, details=True)["checks"]}

    assert "ЛЕНТА" in checks["examples_dupes"]["detail"]
    assert "СТАРЫЙ_МЕРЧАНТ" in checks["merchant_cache_dead"]["detail"]


def test_cli_doctor_default_hides_raw_text(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "spend.db"
    _db_with_sensitive_rows(db_path)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db_path))

    rc = cli.main(["doctor"])
    out = capsys.readouterr().out

    assert rc in (0, 1)
    assert "merchant_cache_dead" in out
    assert "ЛЕНТА" not in out and "СТАРЫЙ_МЕРЧАНТ" not in out
    assert "--details" in out  # подсказка, как увидеть подробности


def test_cli_doctor_details_shows_key_hash_not_raw_merchant(tmp_path, monkeypatch, capsys):
    """--details — явный opt-in: описания примеров видны, но ключ кэша (часто = полное
    описание операции с ФИО/номером) показывается хэшем `key:<sha1[:8]>`, не сырым текстом."""
    db_path = tmp_path / "spend.db"
    _db_with_sensitive_rows(db_path)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db_path))

    cli.main(["doctor", "--details"])
    out = capsys.readouterr().out

    assert "ЛЕНТА" in out                 # examples_dupes — под явным флагом можно
    assert "key:" in out                  # merchant_cache_dead — только хэш
    assert "СТАРЫЙ_МЕРЧАНТ" not in out


def test_cli_doctor_json_default_hides_raw_text(tmp_path, monkeypatch, capsys):
    """Машинный контракт `--json` по умолчанию тоже минимизирован (privacy pack)."""
    db_path = tmp_path / "spend.db"
    _db_with_sensitive_rows(db_path)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db_path))

    cli.main(["doctor", "--json"])
    data = json.loads(capsys.readouterr().out)
    checks = {c["id"]: c for c in data["checks"]}

    assert checks["examples_dupes"]["count"] == 1
    assert "ЛЕНТА" not in checks["examples_dupes"]["detail"]
    assert "СТАРЫЙ_МЕРЧАНТ" not in checks["merchant_cache_dead"]["detail"]


def test_health_data_requests_minimal_details(tmp_path, monkeypatch):
    """`GET /health/data` не отдаёт сырые detail: API идёт тем же минимумом, что и CLI."""
    seen = {}

    def fake_run_checks(**kwargs):
        seen.update(kwargs)
        return {"status": "ok", "checks": []}

    monkeypatch.setattr(doctor, "run_checks", fake_run_checks)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "health.db"))
    Store(tmp_path / "health.db").close()

    r = TestClient(app).get("/health/data?fresh=1")

    assert r.status_code == 200
    assert seen.get("details") is False
