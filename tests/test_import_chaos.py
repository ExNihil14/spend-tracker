"""Chaos/robustness импорта (§G-3): битые кодировки, CR/мусор в полях, лимиты, пустышки,
параллельная запись UI во время импорта. Инвариант: никаких исключений из-за данных,
мусор — в причины пропуска, а не в БД и не в трейсбек.
"""
from __future__ import annotations

import threading
import time

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
    """Битый байт после cp1251-текста — errors=replace, импорт продолжается."""
    raw = (SBER + "\n1;01.09.2026;1234;Выполнено;-100,00;RUB;X;МАГАЗИН\n").encode("cp1251") + b"\xff"
    store = _fresh(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub)
        assert result["status"] == "ok" and result["added"] == 1
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
    """Произвольные байты: известный статус, никакого мусора в датах."""
    assume(len(blob) < MAX_CSV_BYTES)  # лимит входа проверяется отдельным тестом выше
    store = _fresh(tmp_path)
    try:
        result = import_csv(blob, store, taxonomy=TAX, classify=_stub)
        assert result["status"] in ("ok", "empty", "format_error")
        bad = store.conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE date NOT GLOB '____-__-__'").fetchone()["c"]
        assert bad == 0
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
