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


def test_cli_import_cp1251_file_and_real_filename(tmp_path, monkeypatch, capsys):
    """CLI-импорт: cp1251-файл читается (bytes-путь), имя партии — из файла (ресёрч слоёв 23.09)."""
    db = tmp_path / "imp.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    csv_text = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
                "Валюта операции;Категория;Описание\n"
                "1;01.09.2026 10:00;1234;Выполнено;-100,00;RUB;X;ЛЕНТА\n")
    path = tmp_path / "выписка_сентябрь.csv"
    path.write_bytes(csv_text.encode("cp1251"))

    assert cli.main(["import", str(path)]) == 0
    assert "добавлено" in capsys.readouterr().out

    s = Store(db_path=db)
    assert s.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 1
    filename = s.conn.execute("SELECT filename FROM import_batches").fetchone()["filename"]
    assert filename == "выписка_сентябрь.csv"
    s.close()


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
