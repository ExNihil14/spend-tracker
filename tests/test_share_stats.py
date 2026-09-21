"""Метрики-прокси без телеметрии (POLISH_PLAN #13): `doctor --share` — сводка без чувствительных данных, офлайн."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from spendtrack import cli
from spendtrack.doctor import build_usage_summary, usage_issue_url
from spendtrack.store import Store

_LLM_ENV = (
    "SPENDTRACK_LLM_BASE_URL", "SPENDTRACK_LLM_MODEL", "SPENDTRACK_LLM_API_KEY",
    "SPENDTRACK_LLM_PROVIDER", "SPENDTRACK_FREEL_LLM_API_KEY",
    "SPENDTRACK_OPENROUTER_API_KEY", "SPENDTRACK_ALLOW_LOCAL_LLM",
)


def _isolate_llm(monkeypatch) -> None:
    for var in _LLM_ENV:
        monkeypatch.delenv(var, raising=False)


def _secret_db(path) -> None:
    today = datetime.now(UTC).date()
    store = Store(db_path=path)
    store.add_transaction(
        date=(today - timedelta(days=100)).isoformat(),
        description="СЕКРЕТНЫЙ МАГАЗИН", amount_kopecks=-123456,
        category="groceries", category_source="manual",
        merchant="СЕКРЕТ", account_anon="acc_deadbeef")
    store.add_transaction(
        date=today.isoformat(), description="ВТОРАЯ ОПЕРАЦИЯ",
        amount_kopecks=-50, category="other", category_source="manual")
    store.close()


def test_summary_counts_and_buckets(tmp_path, monkeypatch):
    _isolate_llm(monkeypatch)
    db = tmp_path / "spend.db"
    _secret_db(db)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    usage = build_usage_summary()
    assert usage["tx_total"] == 2 and usage["tx_imported"] == 0
    assert usage["categories_used"] == 2 and usage["pending"] == 0
    assert usage["llm_mode"] == "off"
    assert usage["history"] == "91–365 дней"
    assert usage["mode"] in ("repo", "installed")
    assert usage["schema_version"] > 0
    assert usage["categories_total"] and usage["rules"]


def test_summary_empty_db(tmp_path, monkeypatch):
    _isolate_llm(monkeypatch)
    db = tmp_path / "spend.db"
    Store(db_path=db).close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    usage = build_usage_summary()
    assert usage["tx_total"] == 0 and usage["history"] == "нет данных"
    assert usage["backup_local"] is False


def test_summary_has_no_sensitive_values(tmp_path, monkeypatch):
    """В сводке не должно быть сумм, описаний, мерчантов, счетов, категорий по именам и путей."""
    _isolate_llm(monkeypatch)
    db = tmp_path / "spend.db"
    _secret_db(db)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    blob = json.dumps(build_usage_summary(), ensure_ascii=False)
    for forbidden in ("СЕКРЕТ", "123456", "1234.56", "acc_deadbeef", "groceries", str(db)):
        assert forbidden not in blob


def test_summary_broken_db_declared_unavailable(tmp_path, monkeypatch):
    _isolate_llm(monkeypatch)
    db = tmp_path / "broken.db"
    db.write_bytes(b"not a database")
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    usage = build_usage_summary()
    assert usage["db"] == "unavailable" and "tx_total" not in usage


def test_issue_url_prefilled():
    url = usage_issue_url({"version": "0.1.0", "tx_total": 3})
    assert url.startswith("https://github.com/ExNihil14/spend-tracker/issues/new?")
    assert "title" in url and "body" in url and "tx_total" in url
    assert len(url) < 4000


def test_cli_share_human(tmp_path, monkeypatch, capsys):
    _isolate_llm(monkeypatch)
    db = tmp_path / "spend.db"
    _secret_db(db)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    assert cli.main(["doctor", "--share"]) == 0
    out = capsys.readouterr().out
    assert "Анонимная статистика" in out and "issues/new" in out
    assert "СЕКРЕТ" not in out and "acc_deadbeef" not in out


def test_cli_share_json(tmp_path, monkeypatch, capsys):
    _isolate_llm(monkeypatch)
    db = tmp_path / "spend.db"
    _secret_db(db)
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    assert cli.main(["doctor", "--share", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["usage"]["tx_total"] == 2
    assert body["usage_issue_url"].startswith("https://github.com/ExNihil14/spend-tracker/issues/new?")


def test_cli_without_share_has_no_usage(tmp_path, monkeypatch, capsys):
    _isolate_llm(monkeypatch)
    db = tmp_path / "spend.db"
    Store(db_path=db).close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    assert cli.main(["doctor", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert "usage" not in body and "usage_issue_url" not in body
