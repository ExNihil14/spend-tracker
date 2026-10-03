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


def test_cli_goal_add_list_allocate(cli_db, capsys):
    """Ф1 целей: CLI goal add/allocate/list — публичный интерфейс (машинные суммы)."""
    assert cli.main(["goal", "add", "Отпуск", "--target", "100 000"]) == 0
    assert cli.main(["goal", "allocate", "1", "25 000"]) == 0
    assert cli.main(["goal", "list"]) == 0
    out = capsys.readouterr().out
    assert "Отпуск" in out and "25%" in out

    assert cli.main(["goal", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["pct"] == 25 and payload[0]["allocated_kopecks"] == 2_500_000

    assert cli.main(["goal", "archive", "1"]) == 0
    assert cli.main(["goal", "list"]) == 0
    assert "Целей нет" in capsys.readouterr().out


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


def test_cli_backup_creates_snapshot(cli_db, capsys):
    """`spendtrack backup` доступен установкам через uv tool (P1-3): снимок рядом с БД."""
    assert cli.main(["backup"]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    # C1 (Astra 01.10): снимки — в подпапке своей БД (<parent>/backup/<stem>/)
    assert len(list((cli_db.parent / "backup" / cli_db.stem).glob("spend-*.db"))) == 1


def test_cli_backup_drill_runs_restore_check(cli_db, capsys):
    """C2: `backup --drill` — снимок + проверка восстановимости (маркер для doctor)."""
    assert cli.main(["backup", "--drill"]) == 0
    out = capsys.readouterr().out
    assert "restore-drill: ok" in out
    bdir = cli_db.parent / "backup" / cli_db.stem
    marker = json.loads((bdir / "last_restore_drill.json").read_text(encoding="utf-8"))
    assert marker["status"] == "ok"


def test_cli_backup_missing_db_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "nope.db"))
    assert cli.main(["backup"]) == 1
    assert "не найдена" in capsys.readouterr().err


def test_cli_anonymize_writes_sample_with_warning(tmp_path, capsys):
    """`spendtrack anonymize` — образец для issue; с датами/суммами предупреждает в stderr (K2)."""
    src = tmp_path / "statement.csv"
    src.write_text(
        "Дата операции;Номер карты;Статус;Сумма операции;Описание\n"
        "01.09.2026;4111111111111111;Выполнено;-1234,56;ЛЕНТА ПЯТЁРОЧКА\n"
        "02.09.2026;4111111111111111;Выполнено;-500,00;КАФЕ МОЛОКО\n",
        encoding="utf-8")

    assert cli.main(["anonymize", str(src), "--rows", "1"]) == 0
    captured = capsys.readouterr()
    dst = tmp_path / "statement.anon.csv"
    text = dst.read_text(encoding="utf-8")
    assert "ЛЕНТА" not in text and "4111111111111111" not in text
    assert len(text.splitlines()) == 2  # шапка + 1 строка
    assert "строк 1 из 2" in captured.out
    assert "ВНИМАНИЕ" in captured.err

