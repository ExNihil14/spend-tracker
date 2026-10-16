"""Chaos/robustness импорта (§G-3): битые кодировки, CR/мусор в полях, лимиты, пустышки,
параллельная запись UI во время импорта. Инвариант: никаких исключений из-за данных,
мусор — в причины пропуска, а не в БД и не в трейсбек.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import date

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from spendtrack.csv_import import MAX_CSV_BYTES, ImportLimitError, import_csv
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy

TAX = load_taxonomy()
SBER = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
        "Валюта операции;Категория;Описание")


def _stub(tx, store, taxonomy):
    return {"category": "other", "confidence": 0.5, "merchant": None,
            "source": "llm_pending_review"}


def _fresh(tmp_path):
    return Store(db_path=tmp_path / "chaos.db")


def _count(store: Store) -> int:
    return store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]


def _is_canonical_iso(value: str) -> bool:
    """Каноническая ISO-дата (S9): date.fromisoformat(value).isoformat() == value."""
    try:
        return date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False


def test_cr_inside_field_no_crash(tmp_path):
    """Найденный property-тестом баг: `\\r` в поле ронял csv-парсер (`_csv.Error`) — теперь нормализуем."""
    raw = (SBER + "\n"
           "1;01.09.2026;1234;Выполнено;-100,00;RUB;X;МЕРЧАНТ\rЛИШНЕЕ\n"
           "2;02.09.2026;1234;Выполнено;-200,00;RUB;X;КАФЕ\n")
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok"
        assert _count(store) >= 1  # валидная строка импортирована, осколок — в причины
    finally:
        store.close()


def test_crlf_statement_imports_and_stays_iso(tmp_path):
    """CRLF-выписка (Excel/Windows): импортируется, даты в БД — ISO, счётчик строк верный."""
    raw = (SBER + "\r\n1;01.09.2026;1234;Выполнено;-100,00;RUB;X;МАГАЗИН\r\n").encode("cp1251")
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok" and result["added"] == 1
        assert store.conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE date='2026-09-01'").fetchone()["c"] == 1
    finally:
        store.close()


def test_broken_bytes_fall_back_and_survive(tmp_path):
    """Битый байт (0x98 не существует в cp1251) ВНУТРИ поля — errors=replace, строка сохраняется.

    S5 (Astra 01.10): `b"\\xff"` в cp1251 — валидная «я», тест не проверял replacement-политику.
    """
    head = (SBER + "\n1;01.09.2026;1234;Выполнено;-100,00;RUB;X;МАГАЗ").encode("cp1251")
    raw = head + b"\x98" + "ИН\n".encode("cp1251")
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok" and result["added"] == 1
        desc = store.conn.execute("SELECT description FROM transactions").fetchone()["description"]
        assert "МАГАЗ" in desc and "ИН" in desc  # строка сохранена, битый байт заменён
    finally:
        store.close()


def test_priorbank_broken_amount_no_crash(tmp_path):
    """Приорбанк (PDF-мост): битая сумма → amount_unparsed (не 500); cp1251 читается;
    служебные строки без даты — не операции."""
    from synth_bank import gen_priorbank

    raw = gen_priorbank(n=3, seed=5).replace("ЕВРООПТ;BYN, Минск;1,577.92;",
                                             "ЕВРООПТ;BYN, Минск;abc;", 1)
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw.encode("cp1251"), store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok" and result["bank"] == "priorbank"
        assert result["reasons"].get("amount_unparsed") == 1
        assert result["reasons"].get("status") == 3  # Входящий/Итого/Исходящий
        assert _count(store) == 5  # 6 операций − 1 битая
    finally:
        store.close()


def test_priorbank_extra_cell_is_format_error(tmp_path):
    """C3 (адъюдикация wave13): лишняя ячейка в строке (незакавыченный разделитель) — не тихий
    сдвиг полей с подменой знака/суммы, а format_error на весь файл; в БД — ничего."""
    from synth_bank import gen_priorbank

    base = gen_priorbank(n=3, seed=5)
    raw = base.replace(";1,577.92;0.00;0.00;Приорбанк;",
                       ";1,577.92;0.00;0.00;Приорбанк;ЛИШНЕЕ;", 1)
    assert raw != base, "мутация не применилась — тест не о том"
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "format_error", "сдвиг полей должен быть видимой ошибкой формата"
        assert _count(store) == 0
    finally:
        store.close()


def test_quoted_delimiter_field_still_imports(tmp_path):
    """C3-контроль: корректно закавыченное поле с `;` внутри — не «лишняя ячейка»: импорт не ломается."""
    raw = (SBER + '\n1;01.09.2026;1234;Выполнено;-100,00;RUB;X;"МАГАЗИН;ОПТ"\n')
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok" and result["added"] == 1
        row = store.conn.execute("SELECT description FROM transactions").fetchone()
        assert row["description"] == "МАГАЗИН;ОПТ"
    finally:
        store.close()


def test_huge_description_does_not_crash(tmp_path):
    raw = SBER + "\n1;01.09.2026;1234;Выполнено;-100,00;RUB;X;" + "О" * 20_000 + "\n"
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok" and result["added"] == 1
    finally:
        store.close()


def test_over_limit_raises_and_db_untouched(tmp_path):
    store = _fresh(tmp_path)
    try:
        with pytest.raises(ImportLimitError):
            import_csv(b"x" * (MAX_CSV_BYTES + 1), store, taxonomy=TAX, classify=_stub)
        assert _count(store) == 0
    finally:
        store.close()


def test_empty_and_header_only_are_empty_not_error(tmp_path):
    store = _fresh(tmp_path)
    try:
        assert import_csv(b"", store, taxonomy=TAX, classify=_stub)["status"] == "empty"
        assert import_csv(SBER + "\n", store, taxonomy=TAX, classify=_stub)["status"] == "empty"
        assert _count(store) == 0
    finally:
        store.close()


@given(st.binary(max_size=600))
@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
def test_random_bytes_never_raise(tmp_path, blob):
    """Произвольные байты: известный статус, никакого мусора в датах.

    S9 (адъюдикация wave13): прежняя проверка `date NOT GLOB '____-__-__'` была НЕВЕРНА — в SQLite
    `_` в GLOB не подстановка, шаблон не матчил каноническую ISO-дату (тест был зелёным только
    вакуумно, на пустой таблице). Канон: `date.fromisoformat(value).isoformat() == value`.
    """
    assume(len(blob) < MAX_CSV_BYTES)  # лимит входа проверяется отдельным тестом выше
    store = _fresh(tmp_path)
    try:
        result = import_csv(blob, store, taxonomy=TAX, classify=_stub)
        assert result["status"] in ("ok", "empty", "format_error")
        dates = [r["date"] for r in store.conn.execute("SELECT date FROM transactions")]
        assert all(_is_canonical_iso(d) for d in dates), dates[:5]
    finally:
        store.close()


def test_priorbank_structural_mutations_keep_invariants(tmp_path):
    """S9 (адъюдикация wave13): структурные мутации допустимой выписки Приорбанка — инварианты
    держатся: импорт не бросает, статус известный, все даты в БД канонические ISO."""
    from synth_bank import gen_priorbank

    base = gen_priorbank(n=5, seed=5)
    mutations = {
        "bad_amount_comma": base.replace("1,577.92", "12,34", 1),
        "bad_calendar_date": re.sub(r"\b\d{2}\.\d{2}\.\d{4}\b", "31.02.2026", base, count=1),
        "renamed_spis": base.replace("Обороты Списание", "Списание", 1),
        "renamed_account_yo": base.replace("Счет", "Счёт", 1),
        "crlf": base.replace("\n", "\r\n"),
    }
    for name, raw in mutations.items():
        store = _fresh(tmp_path)
        try:
            result = import_csv(raw.encode("utf-8"), store, taxonomy=TAX, classify=_stub)
            assert result["status"] in ("ok", "empty", "format_error"), f"{name}: {result['status']}"
            dates = [r["date"] for r in store.conn.execute("SELECT date FROM transactions")]
            assert all(_is_canonical_iso(d) for d in dates), f"{name}: неканоническая дата {dates[:3]}"
        finally:
            store.close()


def test_parallel_write_during_import(tmp_path):
    """Параллельная UI-запись во время импорта: busy_timeout ждёт commit, исключений нет,
    обе строки на месте (импорт держит write-транзакцию дольше за счёт classify)."""
    db = tmp_path / "par.db"
    store = Store(db_path=db)
    writer_err: list[BaseException] = []

    def slow_classify(tx, st_, tax):
        time.sleep(0.6)
        return {"category": "other", "confidence": 0.5, "merchant": None,
                "source": "llm_pending_review"}

    def writer():
        time.sleep(0.2)
        try:
            other = Store(db_path=db)
            try:
                other.add_transaction(date="2026-09-10", description="UI-ЗАПИСЬ",
                                      amount_kopecks=-300, category="other",
                                      category_source="manual")
            finally:
                other.close()
        except BaseException as e:  # noqa: BLE001 — тест должен увидеть любую ошибку потока
            writer_err.append(e)

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        raw = SBER + "\n1;01.09.2026;1234;Выполнено;-100,00;RUB;X;ИМПОРТ\n"
        result = import_csv(raw, store, taxonomy=TAX, classify=slow_classify)
    finally:
        thread.join()
    try:
        assert result["status"] == "ok"
        assert writer_err == []
        descs = {r["description"] for r in store.conn.execute("SELECT description FROM transactions")}
        assert {"ИМПОРТ", "UI-ЗАПИСЬ"} <= descs
    finally:
        store.close()
