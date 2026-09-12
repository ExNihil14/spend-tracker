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