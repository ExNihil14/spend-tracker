"""W1 ресёрча ошибок (RESEARCH_ERROR_HANDLING_2026-10-04): глобальные handler'ы.

Красные тесты написаны до фиксов (TDD): 500/503 с понятным телом, лог без query,
занятая БД — реальный сценарий, CLI — без трейсбека.
"""
from __future__ import annotations

import logging
import sqlite3
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from spendtrack import cli, errors
from spendtrack.deps import get_store
from spendtrack.main import app
from spendtrack.store import Store


class _BoomStore:
    """Store-заглушка: любой вызов метода — необработанный RuntimeError."""

    def __getattr__(self, name):
        def _raise(*_a, **_k):
            raise RuntimeError("boom")
        return _raise


class _BusyStore:
    """Store-заглушка: любой вызов — sqlite3.OperationalError."""

    def __getattr__(self, name):
        def _raise(*_a, **_k):
            raise sqlite3.OperationalError("database is locked")
        return _raise


@pytest.fixture()
def client():
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_unhandled_error_api_json_and_log_without_query(client, caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger("spendtrack"), "propagate", True)  # lifespan мог выключить
    app.dependency_overrides[get_store] = lambda: _BoomStore()
    canary = "PRIVATE_QUERY_CANARY_7421"  # ASCII: не кодируется — ловится и при логе полного URL
    encoded = quote("СЕКРЕТ", safe="")    # percent-encoded форма (дыра, найденная Astra site_tail 05.10)
    with caplog.at_level(logging.WARNING, logger="spendtrack"):
        r = client.post(f"/api/transactions?q={canary}&note=СЕКРЕТ", json={
            "date": "2026-09-01", "description": "X", "amount": "-1.00"})
    assert r.status_code == 500
    assert r.json()["detail"] == errors.text("internal")  # текст — из реестра (W2)
    assert "/api/transactions" in caplog.text  # путь в логе есть
    assert canary not in caplog.text          # query — ни в сыром ASCII-виде
    assert "СЕКРЕТ" not in caplog.text        # ни в сырой кириллице
    assert encoded not in caplog.text         # ни в percent-encoded виде (encoded-секрет тоже виден)


def test_unhandled_error_hx_returns_json(client):
    app.dependency_overrides[get_store] = lambda: _BoomStore()
    r = client.post("/api/transactions", headers={"hx-request": "true"},
                    json={"date": "2026-09-01", "description": "X", "amount": "-1.00"})
    assert r.status_code == 500 and "detail" in r.json()


def test_unhandled_error_browser_returns_html_page(client):
    app.dependency_overrides[get_store] = lambda: _BoomStore()
    r = client.get("/")
    assert r.status_code == 500 and 'role="alert"' in r.text


def test_operational_error_stub_returns_503(client):
    app.dependency_overrides[get_store] = lambda: _BusyStore()
    r = client.post("/api/transactions", json={
        "date": "2026-09-01", "description": "X", "amount": "-1.00"})
    assert r.status_code == 503 and r.json()["detail"] == errors.text("db_busy")


def test_real_busy_db_returns_503(client, tmp_path):
    """Занятая БД (BEGIN IMMEDIATE вторым соединением + короткий busy_timeout) → 503."""
    db = tmp_path / "busy.db"
    store = Store(db_path=db)
    store.conn.execute("PRAGMA busy_timeout=50")  # в тесте не ждём 5 с
    app.dependency_overrides[get_store] = lambda: store
    holder = sqlite3.connect(db)
    holder.execute("BEGIN IMMEDIATE")
    try:
        r = client.post("/api/transactions", json={
            "date": "2026-09-01", "description": "X", "amount": "-1.00"})
        assert r.status_code == 503 and r.json()["detail"] == errors.text("db_busy")
    finally:
        holder.rollback()
        holder.close()
        store.close()


def test_cli_busy_db_friendly_error(tmp_path, monkeypatch, capsys):
    """W1: занятая БД в CLI — человеческое сообщение и rc=1, а не трейсбек."""
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "cli.db"))

    def _boom(self, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Store, "add_transaction", _boom)
    assert cli.main(["add", "-1", "тест"]) == 1
    err = capsys.readouterr().err
    assert "занята" in err and "Traceback" not in err
