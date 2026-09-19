from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from spendtrack.store import Store

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 6, 15)  # фиксированная дата: проверяем окна дайджеста детерминированно


def _mod():
    spec = importlib.util.spec_from_file_location(
        "demo_data", ROOT / "scripts" / "demo_data.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_gives_feature_rich_profile(tmp_path):
    m = _mod()
    store = Store(db_path=tmp_path / "demo.db")
    try:
        manifest = m.build(store, TODAY)
        probe = m.feature_probe(store, TODAY)
    finally:
        store.close()

    assert probe["transactions"] > 300
    assert probe["recurring"] >= 4 and probe["active_subscriptions"] >= 4
    assert {"large_expense", "price_jump", "near_duplicate"} <= set(probe["anomaly_types"])
    assert probe["pending"] == 6
    assert probe["budgets"] == 5
    assert probe["suggest_candidates"] >= 1
    assert len(manifest["fingerprints"]) == probe["transactions"]


def test_seed_cli_guard_and_if_empty(tmp_path, capsys):
    m = _mod()
    db = tmp_path / "demo.db"

    assert m.main(["seed", "--db", str(db)]) == 0
    assert "verify: все витринные фичи на месте" in capsys.readouterr().out

    assert m.main(["seed", "--db", str(db)]) == 3  # не перезаписываем молча
    assert m.main(["seed", "--db", str(db), "--if-empty"]) == 0
    assert "пропуск" in capsys.readouterr().out


def test_clean_removes_seeded_rows(tmp_path, capsys):
    m = _mod()
    db = tmp_path / "demo.db"
    assert m.main(["seed", "--db", str(db)]) == 0
    capsys.readouterr()

    assert m.main(["clean", "--db", str(db)]) == 0

    store = Store(db_path=db)
    try:
        assert store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 0
        assert store.budget_map() == {}
        assert store.conn.execute("SELECT COUNT(*) c FROM examples").fetchone()["c"] == 0
        assert store.conn.execute("SELECT COUNT(*) c FROM import_batches").fetchone()["c"] == 0
    finally:
        store.close()
    assert not m.manifest_path(db).exists()


def test_seed_force_is_idempotent_and_writes_manifest(tmp_path, capsys):
    m = _mod()
    db = tmp_path / "demo.db"
    assert m.main(["seed", "--db", str(db)]) == 0
    capsys.readouterr()

    assert m.main(["seed", "--db", str(db), "--force"]) == 0  # повторный сид не плодит дублей

    store = Store(db_path=db)
    try:
        probe = m.feature_probe(store, TODAY)
    finally:
        store.close()
    manifest = _mod().manifest_path(db).read_text(encoding="utf-8")
    assert probe["transactions"] > 300
    assert '"batch": "b_' in manifest
    assert len(manifest) > 100


def test_seed_with_fixed_date_is_deterministic(tmp_path, capsys):
    m = _mod()
    db = tmp_path / "demo.db"
    assert m.main(["seed", "--db", str(db), "--date", TODAY.isoformat()]) == 0
    capsys.readouterr()

    store = Store(db_path=db)
    try:
        probe = m.feature_probe(store, TODAY)
    finally:
        store.close()
    assert probe["transactions"] == 350
    assert probe["recurring"] == 6
    assert probe["pending"] == 6


def test_status_reports_features(tmp_path, capsys):
    m = _mod()
    db = tmp_path / "demo.db"
    assert m.main(["seed", "--db", str(db)]) == 0
    capsys.readouterr()

    assert m.main(["status", "--db", str(db)]) == 0

    out = capsys.readouterr().out
    assert '"recurring"' in out and '"pending": 6' in out
    assert "manifest: есть" in out
