"""CLI-команды без покрытия (аудит тестирования 23.09, P0): report / count / confirm.

Проверяем публичный интерфейс: `cli.main([...])` → exit-код + stdout (машинный формат сумм).
"""
from __future__ import annotations

import json

import pytest

from spendtrack import cli
from spendtrack.store import Store


@pytest.fixture()
def cli_db(tmp_path, monkeypatch):
    db = tmp_path / "cli.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    s = Store(db_path=db)
    s.add_transaction(date="2026-09-10", description="ЛЕНТА", amount_kopecks=-12345,
                      category="groceries", category_source="rule", confidence=1.0)
    s.add_transaction(date="2026-09-11", description="ЗАРПЛАТА", amount_kopecks=250000,
                      category="income", category_source="rule", confidence=1.0)
    s.close()
    return db


def test_cli_report_prints_totals(cli_db, capsys):
    assert cli.main(["report", "--month", "2026-09"]) == 0
    out = capsys.readouterr().out
    assert "== 2026-09" in out
    assert "income 2500.00" in out
    assert "expense -123.45" in out
    assert "groceries" in out


def test_cli_report_defaults_to_latest_month(cli_db, capsys):
    assert cli.main(["report"]) == 0
    assert "== 2026-09" in capsys.readouterr().out


def test_cli_count_prints_source_json(cli_db, capsys):
    assert cli.main(["count"]) == 0
    assert json.loads(capsys.readouterr().out) == {"rule": 2}


def test_cli_confirm_updates_category_and_reports_not_found(cli_db, capsys):
    s = Store(db_path=cli_db)
    tx_id = s.conn.execute(
        "SELECT id FROM transactions WHERE description='ЛЕНТА'").fetchone()["id"]
    s.close()

    assert cli.main(["confirm", str(tx_id), "household"]) == 0
    assert "confirmed" in capsys.readouterr().out
    s = Store(db_path=cli_db)
    assert s.get_transaction(tx_id)["category"] == "household"
    s.close()

    assert cli.main(["confirm", "999999", "household"]) == 1
    assert "not found" in capsys.readouterr().out
