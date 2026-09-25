"""Property-based тесты парсеров (§G-1, hypothesis).

Инвариант из аудита 24.09: **любой ввод → валидная запись либо `_skip` с известной причиной; никаких
исключений/500, никакого мусора в `date`**. Тесты гоняют публичные входы (parse_amount, sniff_bank, import_csv)
на случайных данных и проверяют именно это.
"""
from __future__ import annotations

from decimal import InvalidOperation

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from spendtrack.csv_import import SKIP_REASONS, import_csv, sniff_bank
from spendtrack.store import Store, fmt_amount, fmt_amount_signed, parse_amount
from spendtrack.taxonomy import load_taxonomy

TAX = load_taxonomy()

# Функциональные фикстуры (tmp_path, taxonomy) в property-тестах — здоровые предупреждения глушим:
# база создаётся на каждом примере намеренно (изоляция).
PROP = settings(max_examples=80, deadline=None,
                suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])


def _stub_classify(tx, store, taxonomy):
    return {"category": "other", "confidence": 0.5, "merchant": None,
            "source": "llm_pending_review"}


def _db(tmp_path):
    return Store(db_path=tmp_path / "prop.db")


def _iso_dates_only(store: Store) -> int:
    """Сколько строк в БД с датой НЕ в ISO-формате (инвариант: 0 — иначе месячные фильтры ломаются)."""
    return store.conn.execute(
        "SELECT COUNT(*) c FROM transactions WHERE date NOT GLOB '____-__-__'").fetchone()["c"]


@given(st.text(max_size=200))
@PROP
def test_parse_amount_total_function(text):
    """parse_amount на любом тексте: int или контролируемая InvalidOperation — без прочих исключений."""
    try:
        result = parse_amount(text)
    except InvalidOperation:
        return
    assert isinstance(result, int) and not isinstance(result, bool)


@given(st.integers(min_value=-10**12, max_value=10**12))
@PROP
def test_parse_amount_roundtrip_forms(kopecks):
    """Обе формы вывода читаются обратно без потерь (машинная и отображаемая)."""
    assert parse_amount(fmt_amount(kopecks)) == kopecks
    assert parse_amount(fmt_amount_signed(kopecks)) == kopecks


@given(st.lists(st.dictionaries(st.text(max_size=25), st.text(max_size=25), max_size=12), max_size=6))
@PROP
def test_sniff_bank_total_and_known(rows):
    """sniff_bank на произвольных шапках: None или известный банк, без исключений."""
    bank = sniff_bank(rows)
    assert bank in (None, "sber", "tinkoff", "yandex")


@given(lines=st.lists(st.text(max_size=60), max_size=6))
@PROP
def test_import_random_junk_never_raises(tmp_path, lines):
    """Произвольный «CSV»: известный статус, известные причины, даты в БД только ISO."""
    store = _db(tmp_path)
    try:
        result = import_csv("\n".join(lines), store, taxonomy=TAX, classify=_stub_classify)
        assert result["status"] in ("ok", "empty", "format_error")
        assert result["added"] >= 0 and result["skipped"] >= 0
        assert set(result["reasons"]) <= set(SKIP_REASONS)
        assert _iso_dates_only(store) == 0
    finally:
        store.close()


SBER_HEADER = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
               "Валюта операции;Категория;Описание")


@given(date_cells=st.lists(st.text(max_size=18), min_size=1, max_size=8),
       amount_cells=st.lists(st.text(max_size=12), min_size=1, max_size=8))
@PROP
def test_import_messy_date_and_amount_cells(tmp_path, date_cells, amount_cells):
    """Случайные значения в колонках даты/суммы: партия не падает, мусор — в причины пропуска,
    а не в БД; даты в БД всегда ISO (продолжение P0 «мусорная дата»)."""
    n = min(len(date_cells), len(amount_cells))
    rows = [f"{i};{date_cells[i]};1234;Выполнено;{amount_cells[i]};RUB;X;МЕРЧАНТ {i}"
            for i in range(n)]
    raw = SBER_HEADER + "\n" + "\n".join(rows) + "\n"

    store = _db(tmp_path)
    try:
        result = import_csv(raw, store, taxonomy=TAX, classify=_stub_classify)
        assert result["status"] == "ok"
        assert set(result["reasons"]) <= set(SKIP_REASONS)
        # CR/мусор в ячейках может расщепить строку — точное равенство n не гарантируем,
        # но баланс «добавлено = строк в БД» и «добавлено + пропущено ≥ исходных строк» держим.
        total = store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        assert total == result["added"]
        assert result["added"] + result["skipped"] >= n
        assert _iso_dates_only(store) == 0
        for row in store.conn.execute("SELECT amount_kopecks FROM transactions"):
            assert isinstance(row["amount_kopecks"], int)
    finally:
        store.close()
