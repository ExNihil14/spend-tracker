"""Anonymizer выписок (P1 #3, K2): PII заменены, формат сохранён, образец — валидная фикстура.

CLI-команда — `spendtrack anonymize` (модуль `spendtrack.anonymize`); даты и суммы не обезличиваются,
по умолчанию остаются первые 5 строк, о чём есть явное предупреждение в stderr.
"""
from __future__ import annotations

import pytest
from synth_bank import gen_sber

from spendtrack.anonymize import DEFAULT_ROWS, anonymize_csv, main, run_anonymize
from spendtrack.csv_import import import_csv
from spendtrack.store import Store

CSV = (
    "Номер документа;Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;"
    "Валюта операции;Категория;Описание\n"
    "777;01.09.2026 10:00;01.09.2026;4111111111111111;Выполнено;-1234,56;RUB;Супермаркеты;ЛЕНТА ПЯТЁРОЧКА\n"
    "778;02.09.2026 11:00;02.09.2026;4111111111111111;Выполнено;-500,00;RUB;Супермаркеты;ЛЕНТА ПЯТЁРОЧКА\n"
    "779;03.09.2026 12:00;03.09.2026;4111111111111111;Выполнено;-700,00;RUB;Кафе;КАФЕ МОЛОКО\n"
)


def test_pii_removed_and_format_kept():
    out, _report = anonymize_csv(CSV)
    assert "ЛЕНТА" not in out and "КАФЕ" not in out
    assert "4111111111111111" not in out and ";777;" not in out
    # шапка/даты/суммы/статусы/категории — как в оригинале (образец остаётся валидным CSV)
    assert out.splitlines()[0] == CSV.splitlines()[0]
    assert "01.09.2026" in out and "-1234,56" in out and "Супермаркеты" in out and "Выполнено" in out


def test_same_value_same_pseudonym():
    out, _report = anonymize_csv(CSV)
    lines = out.splitlines()[1:]
    assert lines[0].split(";")[-1] == lines[1].split(";")[-1]
    assert lines[0].split(";")[-1] != lines[2].split(";")[-1]


def test_doc_and_account_columns_replaced():
    out, report = anonymize_csv(CSV)
    row = out.splitlines()[1].split(";")
    assert row[0] == "1"                       # номер документа → порядковый
    assert row[3].startswith("КАРТА_")         # номер карты → псевдоним
    assert report["anonymized"]["Описание"] == "desc"
    assert "Номер карты" in report["anonymized"]


def test_extra_column_flag():
    out, _report = anonymize_csv("ФИО;Сумма операции;Описание\nИванов И.И.;-100;ЛЕНТА\n",
                                 {"фио"})
    assert "Иванов" not in out
    assert "ОПЕРАЦИЯ_" in out


def test_cp1251_input_decoded():
    out, _report = anonymize_csv(CSV.encode("cp1251"))
    assert "ЛЕНТА" not in out
    assert "ОПЕРАЦИЯ_0001" in out


def test_untouched_columns_reported():
    _out, report = anonymize_csv(CSV)
    assert "Дата операции" in report["untouched"]
    assert "Статус" in report["untouched"]


def test_empty_input_returns_empty_report():
    """Пустой ввод — пустой результат без исключений (аудит 23.09, P2)."""
    text, report = anonymize_csv(b"")
    assert text == ""
    assert report == {"anonymized": {}, "untouched": [], "unique": {},
                      "rows_total": 0, "rows_written": 0}


def test_rows_limit_keeps_first_rows_and_counts():
    """--rows N: в файле остаются первые N строк данных; даты/суммы не изменяются (K2)."""
    out, report = anonymize_csv(CSV, max_rows=2)
    assert report["rows_total"] == 3 and report["rows_written"] == 2
    lines = out.splitlines()
    assert len(lines) == 3  # шапка + 2 строки
    assert "01.09.2026" in lines[1] and "02.09.2026" in lines[2]
    assert "03.09.2026" not in out


def test_rows_zero_keeps_all():
    out, report = anonymize_csv(CSV, max_rows=0)
    assert report["rows_written"] == 3
    assert "03.09.2026" in out


def test_negative_rows_rejected(tmp_path, capsys):
    """Отрицательный лимит — ошибка, а не тихий «весь файл» (ревью $0, P1)."""
    with pytest.raises(ValueError):
        anonymize_csv(CSV, max_rows=-1)

    src = tmp_path / "s.csv"
    src.write_text(CSV, encoding="utf-8")
    assert run_anonymize(src, max_rows=-1) == 1
    assert "не может быть отрицательным" in capsys.readouterr().err
    assert not (tmp_path / "s.anon.csv").exists()


def test_cli_output_argument_conflict(tmp_path):
    """OUT и -o одновременно — явная ошибка, а не тихий приоритет одного из них."""
    src = tmp_path / "s.csv"
    src.write_text(CSV, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main([str(src), "a.csv", "-o", "b.csv"])
    assert e.value.code == 2


def test_cli_writes_anon_file_and_reports(tmp_path, capsys):
    """CLI: пишет <имя>.anon.csv, печатает отчёт и предупреждение о датах/суммах (audit 23.09)."""
    src = tmp_path / "statement.csv"
    src.write_text(CSV, encoding="utf-8")

    assert main([str(src)]) == 0
    dst = tmp_path / "statement.anon.csv"
    assert dst.is_file()
    captured = capsys.readouterr()
    assert "Записано:" in captured.out and "Обезличено:" in captured.out
    assert "ВНИМАНИЕ" in captured.err and "даты, суммы" in captured.err

    text = dst.read_text(encoding="utf-8")
    assert "ЛЕНТА ПЯТЁРОЧКА" not in text
    assert "4111111111111111" not in text


def test_cli_custom_out_and_extra_column(tmp_path, capsys):
    """-o и --anon-column: путь настраивается, дополнительная колонка обезличивается."""
    src = tmp_path / "s.csv"
    src.write_text(CSV, encoding="utf-8")
    custom = tmp_path / "custom.csv"

    assert main([str(src), "-o", str(custom), "--anon-column", "Категория"]) == 0
    text = custom.read_text(encoding="utf-8")
    assert "Супермаркеты" not in text


def test_cli_positional_out_and_rows(tmp_path, capsys):
    """`spendtrack anonymize IN OUT --rows N` — позиционный OUT и обрезка строк."""
    src = tmp_path / "s.csv"
    src.write_text(CSV, encoding="utf-8")
    custom = tmp_path / "sample.csv"

    assert main([str(src), str(custom), "--rows", "1"]) == 0
    lines = custom.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # шапка + 1 строка
    captured = capsys.readouterr()
    assert "строк 1 из 3" in captured.out
    assert "оставлено: 1" in captured.err


def test_run_anonymize_default_keeps_5_and_warns(tmp_path, capsys):
    """По умолчанию — первые 5 строк: меньше строк в публичном issue (рекомендация запуска)."""
    src = tmp_path / "long.csv"
    rows = "".join(
        f"{i};0{i}.09.2026;0{i}.09.2026;4111111111111111;Выполнено;-{i}00,00;RUB;X;МАГАЗИН {i}\n"
        for i in range(1, 9)
    )
    src.write_text(CSV.splitlines()[0] + "\n" + rows, encoding="utf-8")

    assert run_anonymize(src) == 0
    dst = tmp_path / "long.anon.csv"
    assert len(dst.read_text(encoding="utf-8").splitlines()) == DEFAULT_ROWS + 1
    captured = capsys.readouterr()
    assert f"строк {DEFAULT_ROWS} из 8" in captured.out
    assert f"оставлено: {DEFAULT_ROWS}" in captured.err


def test_run_anonymize_missing_file_reports_error(tmp_path, capsys):
    assert run_anonymize(tmp_path / "nope.csv") == 1
    assert "не удалось прочитать файл" in capsys.readouterr().err


def test_crlf_terminator_not_doubled(tmp_path):
    """CRLF-выписка (cp1251-экспорт банка) сохраняет «\\r\\n», а не превращается в «\\r\\r\\n»."""
    src = tmp_path / "win.csv"
    src.write_bytes(CSV.replace("\n", "\r\n").encode("cp1251"))

    assert run_anonymize(src, max_rows=0) == 0
    raw = (tmp_path / "win.anon.csv").read_bytes()
    assert raw.count(b"\r\n") == 4  # шапка + 3 строки
    body = raw.replace(b"\r\n", b"")
    assert b"\r" not in body and b"\n" not in body
    assert "ЛЕНТА".encode() not in raw


def test_anonymized_sample_imports_same_shape(tmp_path):
    """Образец — валидная фикстура: импортируется (sber) с теми же датами/суммами/статусами."""
    raw = gen_sber(n=8, seed=11)
    anon, _report = anonymize_csv(raw)

    def stub(tx, store, taxonomy):
        return {"category": "other", "confidence": 0.5, "merchant": None,
                "source": "llm_pending_review"}

    original = Store(db_path=tmp_path / "a.db")
    sample = Store(db_path=tmp_path / "b.db")
    res_orig = import_csv(raw, original, classify=stub)
    res_anon = import_csv(anon, sample, classify=stub)
    assert res_orig["status"] == res_anon["status"] == "ok"
    assert res_orig["added"] == res_anon["added"]
    assert res_orig["skipped"] == res_anon["skipped"]

    def key(t):
        return (t["date"], t["amount_kopecks"])
    assert (sorted(map(key, original.list_transactions(limit=1000)))
            == sorted(map(key, sample.list_transactions(limit=1000))))
    original.close()
    sample.close()
