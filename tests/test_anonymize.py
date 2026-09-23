"""Anonymizer выписок (P1 #3): PII заменены, формат сохранён, образец — валидная фикстура."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from synth_bank import gen_sber

from spendtrack.csv_import import import_csv
from spendtrack.store import Store

ROOT = Path(__file__).resolve().parents[1]

CSV = (
    "Номер документа;Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;"
    "Валюта операции;Категория;Описание\n"
    "777;01.09.2026 10:00;01.09.2026;4111111111111111;Выполнено;-1234,56;RUB;Супермаркеты;ЛЕНТА ПЯТЁРОЧКА\n"
    "778;02.09.2026 11:00;02.09.2026;4111111111111111;Выполнено;-500,00;RUB;Супермаркеты;ЛЕНТА ПЯТЁРОЧКА\n"
    "779;03.09.2026 12:00;03.09.2026;4111111111111111;Выполнено;-700,00;RUB;Кафе;КАФЕ МОЛОКО\n"
)


def _mod():
    spec = importlib.util.spec_from_file_location("anonymize", ROOT / "scripts" / "anonymize.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_pii_removed_and_format_kept():
    out, _report = _mod().anonymize_csv(CSV)
    assert "ЛЕНТА" not in out and "КАФЕ" not in out
    assert "4111111111111111" not in out and ";777;" not in out
    # шапка/даты/суммы/статусы/категории — как в оригинале (образец остаётся валидным CSV)
    assert out.splitlines()[0] == CSV.splitlines()[0]
    assert "01.09.2026" in out and "-1234,56" in out and "Супермаркеты" in out and "Выполнено" in out


def test_same_value_same_pseudonym():
    out, _report = _mod().anonymize_csv(CSV)
    lines = out.splitlines()[1:]
    assert lines[0].split(";")[-1] == lines[1].split(";")[-1]
    assert lines[0].split(";")[-1] != lines[2].split(";")[-1]


def test_doc_and_account_columns_replaced():
    out, report = _mod().anonymize_csv(CSV)
    row = out.splitlines()[1].split(";")
    assert row[0] == "1"                       # номер документа → порядковый
    assert row[3].startswith("КАРТА_")         # номер карты → псевдоним
    assert report["anonymized"]["Описание"] == "desc"
    assert "Номер карты" in report["anonymized"]


def test_extra_column_flag():
    out, _report = _mod().anonymize_csv("ФИО;Сумма операции;Описание\nИванов И.И.;-100;ЛЕНТА\n",
                                        {"фио"})
    assert "Иванов" not in out
    assert "ОПЕРАЦИЯ_" in out


def test_cp1251_input_decoded():
    out, _report = _mod().anonymize_csv(CSV.encode("cp1251"))
    assert "ЛЕНТА" not in out
    assert "ОПЕРАЦИЯ_0001" in out


def test_untouched_columns_reported():
    _out, report = _mod().anonymize_csv(CSV)
    assert "Дата операции" in report["untouched"]
    assert "Статус" in report["untouched"]


def test_empty_input_returns_empty_report():
    """Пустой ввод — пустой результат без исключений (аудит 23.09, P2)."""
    text, report = _mod().anonymize_csv(b"")
    assert text == ""
    assert report == {"anonymized": {}, "untouched": [], "unique": {}}


def test_cli_writes_anon_file_and_reports(tmp_path, capsys):
    """CLI: пишет <имя>.anon.csv и печатает отчёт (аудит 23.09: main() без покрытия)."""
    src = tmp_path / "statement.csv"
    src.write_text(CSV, encoding="utf-8")
    mod = _mod()

    assert mod.main([str(src)]) == 0
    dst = tmp_path / "statement.anon.csv"
    assert dst.is_file()
    out = capsys.readouterr().out
    assert "Записано:" in out and "Обезличено:" in out

    text = dst.read_text(encoding="utf-8")
    assert "ЛЕНТА ПЯТЁРОЧКА" not in text
    assert "4111111111111111" not in text


def test_cli_custom_out_and_extra_column(tmp_path, capsys):
    """--out и --anon-column: путь настраивается, дополнительная колонка обезличивается."""
    src = tmp_path / "s.csv"
    src.write_text(CSV, encoding="utf-8")
    custom = tmp_path / "custom.csv"
    mod = _mod()

    assert mod.main([str(src), "-o", str(custom), "--anon-column", "Категория"]) == 0
    text = custom.read_text(encoding="utf-8")
    assert "Супермаркеты" not in text


def test_anonymized_sample_imports_same_shape(tmp_path):
    """Образец — валидная фикстура: импортируется (sber) с теми же датами/суммами/статусами."""
    raw = gen_sber(n=8, seed=11)
    anon, _report = _mod().anonymize_csv(raw)

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
