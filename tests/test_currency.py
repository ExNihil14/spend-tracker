"""Мультивалютность (#5): валюта хранится/отображается, ₽-агрегации её не смешивают."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from spendtrack import cli
from spendtrack.csv_import import import_csv
from spendtrack.digest import build_digest
from spendtrack.export import CSV_HEADERS, csv_bytes
from spendtrack.main import app
from spendtrack.recurring import detect_recurring
from spendtrack.reports import budgets_progress, report_month
from spendtrack.store import Store, fingerprint, normalize_currency

MONTH = "2026-09"
SBER_USD = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;"
            "Категория;Описание\n"
            "1;01.09.2026;1234;Выполнено;-10,00;USD;Прочее;STEAM\n")
SBER_NO_CURRENCY = ("Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
                    "Категория;Описание\n"
                    "1;01.09.2026;1234;Выполнено;-10,00;Прочее;STEAM\n")


def _classify(tx, store, taxonomy):
    return {"category": "other", "source": "rule", "confidence": 1.0,
            "merchant": None, "review_status": "approved", "category_llm": None}


def _add(store, desc, kopecks, currency="RUB", day="01", merchant=None, category="other"):
    return store.add_transaction(date=f"{MONTH}-{day}", description=desc, amount_kopecks=kopecks,
                                 category=category, category_source="rule", merchant=merchant,
                                 currency=currency)


def test_normalize_currency_aliases():
    assert normalize_currency("₽") == "RUB"
    assert normalize_currency("руб.") == "RUB"
    assert normalize_currency("rub") == "RUB"
    assert normalize_currency("$") == "USD"
    assert normalize_currency("доллар") == "USD"
    assert normalize_currency("eur") == "EUR"
    assert normalize_currency("KZT") == "KZT"
    assert normalize_currency("kgs") == "KGS"
    assert normalize_currency("XYZ") == "XYZ"
    assert normalize_currency("долл") is None
    assert normalize_currency("") is None
    assert normalize_currency(None) is None


def test_fingerprint_rub_unchanged_and_currency_aware():
    legacy = hashlib.sha1("2026-09-01|-100|КОФЕ|acc_x|".encode()).hexdigest()
    assert fingerprint("2026-09-01", -100, "кофе", "acc_x", "") == legacy
    assert fingerprint("2026-09-01", -100, "кофе", "acc_x", "", "USD") != legacy


def test_store_defaults_and_validation(store):
    _add(store, "КОФЕ", -100)
    assert store.conn.execute("SELECT currency FROM transactions").fetchone()["currency"] == "RUB"
    _add(store, "STEAM", -500, currency="usd")
    row = store.conn.execute("SELECT currency FROM transactions WHERE description='STEAM'").fetchone()
    assert row["currency"] == "USD"
    with pytest.raises(ValueError):
        _add(store, "БРАК", -100, currency="долл")


def test_same_amount_different_currency_not_deduped(store):
    assert _add(store, "ПОДПИСКА", -999, currency="RUB") is not None
    assert _add(store, "ПОДПИСКА", -999, currency="USD") is not None
    assert store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 2


def test_migration_v5_adds_currency_with_default(tmp_path):
    db = tmp_path / "v4.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL UNIQUE,
        date TEXT NOT NULL, description TEXT NOT NULL, amount_kopecks INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT 'other', category_source TEXT NOT NULL DEFAULT 'rule',
        confidence REAL NOT NULL DEFAULT 1.0, merchant TEXT, account_anon TEXT, import_batch TEXT,
        created TEXT, updated TEXT, category_llm TEXT,
        review_status TEXT NOT NULL DEFAULT 'approved', statement_order INTEGER)""")
    conn.execute("INSERT INTO transactions (fingerprint,date,description,amount_kopecks,category,"
                 "category_source,confidence,created,updated)"
                 " VALUES ('fp','2026-09-01','СТАР',-100,'other','rule',1.0,'t','t')")
    conn.execute("PRAGMA user_version=4")
    conn.commit()
    conn.close()

    s = Store(db_path=db)
    assert s.conn.execute("PRAGMA user_version").fetchone()[0] == 5
    assert s.conn.execute("SELECT currency FROM transactions WHERE id=1").fetchone()["currency"] == "RUB"
    assert s.conn.execute("SELECT COUNT(*) c FROM transactions WHERE currency IS NULL").fetchone()["c"] == 0
    s.close()


def test_budgets_and_report_ignore_non_rub(store):
    store.set_budget("groceries", 100_000)
    _add(store, "ЛЕНТА", -40_000, category="groceries")
    _add(store, "AMAZON", -90_000, currency="USD", category="groceries")
    prog = budgets_progress(store, MONTH)
    assert prog[0]["spent_k"] == 40_000
    assert report_month(store, MONTH)["expense_k"] == -40_000


def test_digest_ignores_non_rub(store):
    _add(store, "ЛЕНТА", -1_000, category="groceries", day="20")
    _add(store, "AMAZON", -500_000, currency="USD", category="groceries", day="20")
    d = build_digest(store, days=7, today=date(2026, 9, 21))
    assert d["expense_k"] == -1_000
    assert d["transaction_count"] == 1


def test_recurring_ignores_non_rub(store):
    for d in ("2026-07-01", "2026-08-01", "2026-09-01"):
        store.add_transaction(date=d, description="NETFLIX", amount_kopecks=-999,
                              category="subscriptions", category_source="rule",
                              merchant="NETFLIX", currency="RUB")
        store.add_transaction(date=d, description="SPOTIFY", amount_kopecks=-999,
                              category="subscriptions", category_source="rule",
                              merchant="SPOTIFY", currency="USD")
    subs = detect_recurring(store, today=date(2026, 9, 21))
    assert [s["merchant"] for s in subs] == ["NETFLIX"]


def test_import_reads_currency_column(store):
    res = import_csv(SBER_USD, store, bank="sber", classify=_classify)
    assert res["added"] == 1
    assert store.conn.execute("SELECT currency FROM transactions").fetchone()["currency"] == "USD"


def test_import_without_currency_column_defaults_rub(store):
    res = import_csv(SBER_NO_CURRENCY, store, bank="sber", classify=_classify)
    assert res["added"] == 1
    assert store.conn.execute("SELECT currency FROM transactions").fetchone()["currency"] == "RUB"


def test_import_unknown_currency_value_falls_back_to_rub(store):
    csv_text = SBER_USD.replace(";USD;", ";долл;")
    res = import_csv(csv_text, store, bank="sber", classify=_classify)
    assert res["added"] == 1
    assert store.conn.execute("SELECT currency FROM transactions").fetchone()["currency"] == "RUB"


def test_export_has_currency_column(store):
    _add(store, "STEAM", -500, currency="USD")
    rows = csv_bytes(store.export_transactions()).decode("utf-8-sig").splitlines()
    assert rows[0].split(";") == list(CSV_HEADERS)
    assert rows[0].split(";")[3] == "Валюта"
    assert rows[1].split(";")[3] == "USD"


def test_api_currency_roundtrip_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "api.db"))
    client = TestClient(app)
    ok = client.post("/api/transactions", json={"date": "2026-09-01", "description": "STEAM",
                                                "amount": "-5.00", "currency": "usd"})
    assert ok.status_code == 200
    form = client.post("/api/transactions", data={"date": "2026-09-01", "description": "FORM",
                                                  "amount": "-6.00", "currency": "eur"})
    assert form.status_code == 200
    store = Store(db_path=tmp_path / "api.db")
    rows = {r["description"]: r["currency"] for r in
            store.conn.execute("SELECT description, currency FROM transactions")}
    assert rows == {"STEAM": "USD", "FORM": "EUR"}
    store.close()
    bad = client.post("/api/transactions", json={"date": "2026-09-01", "description": "X",
                                                 "amount": "-5.00", "currency": "долл"})
    assert bad.status_code == 422


def test_ui_shows_currency_for_non_rub_and_day_total_is_rub_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "ui.db"))
    store = Store(db_path=tmp_path / "ui.db")
    _add(store, "ЛЕНТА", -1_000)
    _add(store, "AMAZON", -500_000, currency="USD")
    store.close()
    html = TestClient(app).get("/").text
    assert "USD" in html
    assert "\u221210,00 ₽" in html          # дневной итог — только RUB
    assert "\u22125\u00a0010,00" not in html  # USD-сумма в итог не попала


def test_cli_add_currency(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "categorize_transaction", _classify)
    rc = cli.main(["add", "-5.00", "STEAM", "--currency", "usd"])
    assert rc == 0
    assert "USD" in capsys.readouterr().out
    store = Store(db_path=tmp_path / "cli.db")
    assert store.conn.execute("SELECT currency FROM transactions").fetchone()["currency"] == "USD"
    store.close()
    with pytest.raises(SystemExit) as exc:
        cli.main(["add", "-5.00", "X", "--currency", "долл"])
    assert exc.value.code == 2
