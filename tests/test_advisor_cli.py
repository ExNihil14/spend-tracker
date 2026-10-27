from __future__ import annotations

import json
from datetime import date

import pytest

from spendtrack.cli import main
from spendtrack.store import Store

MONTH = date.today().strftime("%Y-%m")  # noqa: DTZ011 - локальная дата в тесте


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = Store(db_path=tmp_path / "cli.db")
    s.add_transaction(f"{MONTH}-05", "x", -100_000, "groceries", "rule")
    monkeypatch.setattr("spendtrack.cli.make_store", lambda: s)
    yield s
    s.close()


def test_ask_text_template(store, capsys):
    rc = main(["ask", "сколько потратил в этом месяце?"])
    out = capsys.readouterr().out
    assert rc == 0 and "1000.00 ₽" in out


def test_ask_json_schema(store, capsys):
    rc = main(["ask", "сколько потратил", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(payload) == {"intent", "period", "answer", "facts"}
    assert payload["facts"]["total"] == 100_000
    assert "merchant" not in payload["facts"]


def test_ask_month_override(store, capsys):
    store.add_transaction("2026-09-05", "x", -50_000, "restaurants", "rule")
    rc = main(["ask", "сколько в этом месяце", "--month", "2026-09", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["period"]["month"] == "2026-09"


@pytest.mark.parametrize("month", ["2026-13", "2026-9", "bad"])
def test_ask_invalid_month(store, capsys, month):
    rc = main(["ask", "сколько", "--month", month])
    assert rc == 2


def test_ask_unknown_ask_back(store, capsys):
    rc = main(["ask", "что происходит?"])
    out = capsys.readouterr().out
    assert rc == 3 and "Уточни" in out


def test_ask_no_llm_flag(store, capsys):
    rc = main(["ask", "сколько потратил", "--no-llm"])
    assert rc == 0
    assert "1000.00 ₽" in capsys.readouterr().out


def test_ask_requires_question(store):
    with pytest.raises(SystemExit) as exc:
        main(["ask"])
    assert exc.value.code == 2


def test_ask_category(store, capsys):
    rc = main(["ask", "сколько на продукты в этом месяце?"])
    out = capsys.readouterr().out
    assert rc == 0 and "Продукты" in out
