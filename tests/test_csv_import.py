from __future__ import annotations

from spendtrack.csv_import import import_csv, sniff_bank
from spendtrack.store import parse_amount

SBER_CSV = """Номер документа;Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;Валюта операции;Сумма платежа;Валюта платежа;Категория;Описание
1;01.09.2026 10:00;01.09.2026;1234;Выполнено;-1234,50;RUB;-1234,50;RUB;Продукты;ЛЕНТА
2;01.09.2026 11:00;01.09.2026;1234;Выполнено;250000,00;RUB;250000,00;RUB;Зарплата;ЗАРАБОТНАЯ ПЛАТА
"""

TINKOFF_CSV = """Дата;Сумма операции;Категория;Описание;Счёт
02.09.2026;-1200,00;Транспорт;UBER MUNCHEN;40817810000000000000
02.09.2026;-1549,00;Подписки;NETFLIX.COM;40817810000000000000
"""


def _stub_classify():
    """Оффлайн-классификатор для тестов импорта: никогда не ходит в сеть."""

    def classify(tx, store, taxonomy):
        from spendtrack.categorize import categorize_rules_only
        rule = categorize_rules_only(tx, taxonomy, store)
        if rule:
            return {"category": rule, "confidence": 1.0, "merchant": tx.get("merchant"),
                    "reason": "rule", "source": "rule"}
        return {"category": "other", "confidence": 0.5, "merchant": tx.get("merchant"),
                "reason": "stub", "source": "llm_pending_review"}

    return classify


def test_sniff_sber():
    rows = [{"Дата операции": "1", "Описание": "x"}]
    assert sniff_bank(rows) == "sber"


def test_sniff_tinkoff():
    rows = [{"Дата": "1", "Счёт": "c"}]
    assert sniff_bank(rows) == "tinkoff"


def test_import_sber(store):
    res = import_csv(SBER_CSV, store, classify=_stub_classify())
    assert res["status"] == "ok"
    assert res["added"] == 2
    assert res["dupes"] == 0
    tx = store.list_transactions()
    by_amount = {t["amount_kopecks"]: t for t in tx}
    assert by_amount[parse_amount("-1234.50")]["category"] == "groceries"
    assert by_amount[parse_amount("250000")]["category"] == "income"


def test_import_tinkoff(store):
    res = import_csv(TINKOFF_CSV, store, classify=_stub_classify())
    assert res["bank"] == "tinkoff"
    assert res["added"] == 2


def test_import_rerun_is_noop(store):
    c = _stub_classify()
    assert import_csv(SBER_CSV, store, classify=c)["added"] == 2
    res = import_csv(SBER_CSV, store, classify=c)
    assert res["added"] == 0
    assert res["dupes"] == 2


def test_import_empty(store):
    res = import_csv("", store)
    assert res["status"] == "empty"


def test_same_day_repeat_not_deduped(store):
    """Fable review: два одинаковых кофе в один день — легитимные повторы, не дубли."""
    csv_text = SBER_CSV + "3;01.09.2026 12:00;01.09.2026;1234;Выполнено;-1234,50;RUB;-1234,50;RUB;Продукты;ЛЕНТА\n"
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 3


def test_whitespace_normalized_not_deduped_different(store):
    """Fable review: реэкспорт с изменёнными пробелами = тот же дедуп."""
    csv_text = SBER_CSV.replace(" 10:00", "  10:00   ").replace("ЛЕНТА\n2", "ЛЕНТА\n2")
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 2


def test_sber_thousand_separator_space(store):
    """Реальный Сбербанк: пробел-разделитель тысяч в сумме (-1 234,56)."""
    csv_text = """Номер документа;Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;Валюта операции;Сумма платежа;Валюта платежа;Категория;Описание
1;01.09.2026 10:00;01.09.2026;1234;Выполнено;-1 234,56;RUB;-1 234,56;RUB;Продукты;ЛЕНТА
2;02.09.2026 11:00;02.09.2026;1234;Выполнено;25 000,00;RUB;25 000,00;RUB;Зарплата;ЗАРАБОТНАЯ ПЛАТА
"""
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 2
    by_amount = {t["amount_kopecks"]: t for t in store.list_transactions()}
    assert -123456 in by_amount
    assert 2500000 in by_amount


def test_sber_non_breaking_space_separator(store):
    """Сбер использует NBSP (\\u00a0) как разделитель тысяч в суммах."""
    csv_text = """Номер документа;Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;Валюта операции;Сумма платежа;Валюта платежа;Категория;Описание
1;01.09.2026 10:00;01.09.2026;1234;Выполнено;-1\u00a0234,56;RUB;-1\u00a0234,56;RUB;Продукты;ЛЕНТА
"""
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 1
    assert -123456 in {t["amount_kopecks"] for t in store.list_transactions()}


def test_sber_dates_stored_iso(store):
    """Реальная выписка: DD.MM.YYYY → ISO; иначе month-фильтры и дашборд ломаются."""
    import_csv(SBER_CSV, store, classify=_stub_classify())
    dates = {t["date"] for t in store.list_transactions()}
    assert dates == {"2026-09-01"}
    assert len(store.list_transactions(month="2026-09")) == 2


def test_sber_pending_status_skipped(store):
    """«В обработке» — не проведённая операция, в БД не попадает."""
    csv_text = SBER_CSV + (
        "3;03.09.2026 12:00;03.09.2026;1234;В обработке;-500,00;RUB;-500,00;RUB;Продукты;МАГНИТ\n"
    )
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 2
    assert all("МАГНИТ" not in t["description"] for t in store.list_transactions())


def test_cp1251_bytes_decoded(store):
    """Файл Сбербанка в cp1251: кириллица должна декодироваться (иначе правила/LLM слепнут)."""
    csv_text = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;-100,00;RUB;ЛЕНТА\n"
    )
    res = import_csv(csv_text.encode("cp1251"), store, classify=_stub_classify())
    assert res["added"] == 1
    assert store.list_transactions()[0]["category"] == "groceries"


def test_unicode_minus_amount(store):
    """Экспорт может использовать типографский минус U+2212 — не должен падать."""
    csv_text = SBER_CSV.replace("-1234,50", "\u22121 234,50")
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 2
    assert parse_amount("-1234.50") in {t["amount_kopecks"] for t in store.list_transactions()}