from __future__ import annotations

import pytest

from spendtrack.csv_import import MAX_CSV_BYTES, import_csv, missing_columns, sniff_bank, summarize
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


def test_reexport_with_shifted_rows_not_duplicated(store):
    """Новая строка сверху сдвигает позиции — дедуп не должен ломаться (occurrence, не rownum)."""
    c = _stub_classify()
    assert import_csv(SBER_CSV, store, classify=c)["added"] == 2
    header, rows = SBER_CSV.split("\n", 1)
    new_line = "0;30.08.2026 09:00;30.08.2026;1234;Выполнено;-999,00;RUB;-999,00;RUB;Прочее;НОВОЕ\n"
    res = import_csv(header + "\n" + new_line + rows, store, classify=c)
    assert res["added"] == 1  # только новая строка
    assert res["dupes"] == 2


def test_reexport_with_extra_identical_copy_adds_one(store):
    """В файле стало 2 одинаковых покупки (была 1) → добавляется ровно одна."""
    c = _stub_classify()
    import_csv(SBER_CSV, store, classify=c)
    header, rows = SBER_CSV.split("\n", 1)
    dup_line = "9;01.09.2026 10:00;01.09.2026;1234;Выполнено;-1234,50;RUB;-1234,50;RUB;Продукты;ЛЕНТА\n"
    res = import_csv(header + "\n" + dup_line + rows, store, classify=c)
    assert res["added"] == 1
    assert res["dupes"] == 2


YANDEX_CSV = """datetime;operation;amount;currency;category;title;merchant;description
2026-09-02T10:00:00;payment;-1200.00;RUB;Транспорт;UBER MUNCHEN;UBER;Поездка
"""


def test_import_yandex(store):
    """Yandex-адаптер: snapshot формата (ранее не был покрыт)."""
    res = import_csv(YANDEX_CSV, store, classify=_stub_classify())
    assert res["bank"] == "yandex"
    assert res["added"] == 1
    t = store.list_transactions()[0]
    assert t["date"] == "2026-09-02"
    assert t["amount_kopecks"] == -120000
    assert t["description"] in ("Поездка", "UBER MUNCHEN")


def test_comma_delimiter_with_dot_decimal(store):
    """CSV с запятой-разделителем (и точкой в десятичных) — _guess_sep обрабатывает."""
    csv_text = ("Номер документа,Дата операции,Номер карты,Статус,Сумма операции,Описание\n"
                "1,01.09.2026 10:00,1234,Выполнено,-100.00,ЛЕНТА\n")
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 1
    assert store.list_transactions()[0]["amount_kopecks"] == -10000


def test_sber_rejected_status_skipped(store):
    csv_text = SBER_CSV + "4;04.09.2026 12:00;04.09.2026;1234;Отклонено;-700,00;RUB;-700,00;RUB;Продукты;АШАН\n"
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 2
    assert all("АШАН" not in t["description"] for t in store.list_transactions())

def test_csv_size_limit_rejected(store):
    """Файл больше лимита — явная ошибка, а не OOM/тихий парсинг."""
    with pytest.raises(ValueError):
        import_csv("x" * (MAX_CSV_BYTES + 1), store)


def test_absurd_amount_marked_invalid(store):
    """Мусорная сумма (≈100 млрд руб) — в отчёт invalid, в БД не попадает."""
    csv_text = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;99999999999,99;RUB;Продукты;АНТИКВАРИАТ\n"
        "2;01.09.2026 11:00;1234;Выполнено;-100,00;RUB;Продукты;ЛЕНТА\n")
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["invalid"] == 1
    assert res["added"] == 1
    assert all("АНТИКВАРИАТ" not in t["description"] for t in store.list_transactions())


def test_no_invalid_key_on_clean_import(store):
    res = import_csv(SBER_CSV, store, classify=_stub_classify())
    assert res["invalid"] == 0


def test_size_limit_counts_bytes_not_chars(store):
    """Кириллица = 2 байта/символ: лимит обязан считаться в байтах (P0 ревью 19.09)."""
    cyrillic = "ф" * (MAX_CSV_BYTES // 2 + 1)  # символов ~5 М, байт >10 М
    with pytest.raises(ValueError):
        import_csv(cyrillic, store)


# ── Дрейф формата (P1 #1): явный отчёт вместо тихого мисс-парсинга ───────────

def test_renamed_date_column_reports_format_error(store):
    """Банк переименовал колонку → format_error с просьбой прислать образец, не «0 добавлено»."""
    csv_text = SBER_CSV.replace("Дата операции", "Дата проводки")
    res = import_csv(csv_text, store)
    assert res["status"] == "format_error"
    assert "Дата операции" in res["missing_columns"]
    assert "образец" in res["message"]
    assert res["added"] == 0 and store.list_transactions() == []


def test_removed_amount_column_reports_format_error(store):
    csv_text = ("Номер документа;Дата операции;Номер карты;Статус;Валюта операции;Описание\n"
                "1;01.09.2026 10:00;1234;Выполнено;RUB;ЛЕНТА\n")
    res = import_csv(csv_text, store)
    assert res["status"] == "format_error"
    assert "Сумма операции" in res["missing_columns"]


def test_unknown_headers_auto_reports_format_error(store):
    """Ни один банк не опознан — явная ошибка, а не молчаливый дефолт на sber."""
    csv_text = "Дата проводки;Назначение;Сумма\n01.09.2026;ЛЕНТА;100\n"
    res = import_csv(csv_text, store)
    assert res["status"] == "format_error"
    assert res["bank"] is None
    assert "found_columns" in res and "Дата проводки" in res["found_columns"]
    assert "образец" in res["message"]


def test_explicit_wrong_bank_reports_format_error(store):
    res = import_csv(SBER_CSV, store, bank="tinkoff")
    assert res["status"] == "format_error"
    assert res["bank"] == "tinkoff"


def test_unknown_bank_name_reports_format_error(store):
    res = import_csv(SBER_CSV, store, bank="sber2")
    assert res["status"] == "format_error"
    assert "Неизвестный банк" in res["message"]


def test_ambiguous_column_set_imports_without_format_error(store):
    """Колонки без уникальных маркеров подходят нескольким банкам — это не дрейф, импорт работает."""
    csv_text = "Дата;Сумма;Описание\n01.09.2026;-100,00;ЛЕНТА\n"
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["status"] == "ok"
    assert res["added"] == 1


def test_amount_limit_boundary(store):
    """Ровно лимит — импортируется; лимит+1 копейка — в отчёт amount_limit."""
    csv_text = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;1000000000.00;RUB;Прочее;ЛИМИТ\n"
        "2;01.09.2026 11:00;1234;Выполнено;1000000000.01;RUB;Прочее;СВЕРХ\n")
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["added"] == 1
    assert res["invalid"] == 1
    assert res["reasons"] == {"amount_limit": 1}


def test_missing_columns_helper():
    assert missing_columns("sber", ["Дата операции", "Описание", "Сумма операции"]) == []
    assert missing_columns("sber", ["Дата", "Категория", "Сумма"]) == []
    assert missing_columns("sber", ["Дата операции", "Описание"]) == ["Сумма операции"]


# ── Отчёт импорта «добавлено / пропущено / подозрительно» (P1 #2) ────────────

def test_report_counts_skipped_and_suspicious(store):
    csv_text = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;-100,00;RUB;Продукты;ЛЕНТА\n"            # added
        "2;02.09.2026 10:00;1234;В обработке;-200,00;RUB;Продукты;МАГНИТ\n"        # status
        "3;03.09.2026 10:00;1234;Выполнено;;RUB;Продукты;ПЯТЁРОЧКА\n"              # missing_fields
        "4;04.09.2026 10:00;1234;Выполнено;abc;RUB;Продукты;АШАН\n"                # amount_unparsed
        "5;2026/09/05;1234;Выполнено;-300,00;RUB;Продукты;ОЗОН\n")                 # date_unrecognized
    res = import_csv(csv_text, store, classify=_stub_classify())
    assert res["status"] == "ok"
    assert res["added"] == 2            # ЛЕНТА + ОЗОН (нераспознанная дата импортируется с пометкой)
    assert res["skipped"] == 3
    assert res["suspicious"] == 1
    assert res["reasons"] == {"status": 1, "missing_fields": 1, "amount_unparsed": 1}
    assert res["suspicious_reasons"] == {"date_unrecognized": 1}


def test_summarize_mentions_three_numbers(store):
    csv_text = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;-100,00;RUB;Продукты;ЛЕНТА\n"
        "2;02.09.2026 10:00;1234;В обработке;-200,00;RUB;Продукты;МАГНИТ\n"
        "3;2026/09/05;1234;Выполнено;-300,00;RUB;Продукты;ОЗОН\n")
    res = import_csv(csv_text, store, classify=_stub_classify())
    text = summarize(res)
    assert "+2 добавлено" in text          # ЛЕНТА + ОЗОН (нераспознанная дата — с пометкой)
    assert "1 пропущено" in text and "не проведены банком" in text
    assert "1 подозрительно" in text and "нераспознанная дата" in text
    assert "банк=sber" in text


def test_summarize_format_error_returns_message(store):
    res = import_csv(SBER_CSV.replace("Сумма операции", "Итог"), store)
    assert res["status"] == "format_error"
    assert summarize(res) == res["message"]


def test_summarize_empty():
    assert summarize({"status": "empty"}) == "Пустой файл"


# ── CLI-ветка отчёта ─────────────────────────────────────────────────────────

def test_cli_import_json_format_error(tmp_path, monkeypatch, capsys):
    import json

    bad = tmp_path / "bad.csv"
    bad.write_text("Дата проводки;Назначение;Сумма\n01.09.2026;ЛЕНТА;100\n", encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "cli.db"))
    from spendtrack import cli

    assert cli.main(["import", str(bad), "--json"]) == 1
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "format_error"

    assert cli.main(["import", str(bad)]) == 1
    assert "образец" in capsys.readouterr().err


def test_cli_import_reports_summary(tmp_path, monkeypatch, capsys):
    good = tmp_path / "good.csv"
    good.write_text("Дата;Сумма операции;Категория;Описание;Счёт\n"
                    "02.09.2026;-1200,00;Транспорт;UBER MUNCHEN;4081781\n", encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "cli.db"))
    from spendtrack import cli

    assert cli.main(["import", str(good)]) == 0
    out = capsys.readouterr().out
    assert "Импорт:" in out and "добавлено" in out and "банк=tinkoff" in out


def test_import_commits_batch_transaction(store):
    """Импорт — одна транзакция на партию: после импорта открытых транзакций нет."""
    res = import_csv(SBER_CSV, store, classify=_stub_classify())
    assert res["added"] == 2
    assert store.conn.in_transaction is False


def test_import_rolls_back_on_classify_error(store):
    """Сбой в середине партии: половина строк не оседает в БД, транзакция закрыта."""
    calls = {"n": 0}

    def failing(tx, st, taxonomy):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("сбой классификатора")
        return {"category": "other", "source": "rule", "confidence": 1.0,
                "merchant": None, "review_status": "approved", "category_llm": None}

    with pytest.raises(RuntimeError):
        import_csv(SBER_CSV, store, classify=failing)

    assert store.conn.in_transaction is False
    assert store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 0

