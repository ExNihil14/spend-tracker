"""«Нулевая сеть»: доказательство offline-first — без ключей LLM приложение не делает ни одного outbound-вызова.

Сокеты блокируются на уровне connect/getaddrinfo: любой сетевой вызов = падение теста.
"""
from __future__ import annotations

import socket

from spendtrack.csv_import import import_csv
from spendtrack.store import Store

UNKNOWN_MERCHANT_CSV = (
    "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Категория;Описание\n"
    "1;01.09.2026 10:00;1234;Выполнено;-1234,56;RUB;Прочее;НЕИЗВЕСТНЫЙ МЕРЧАНТ БЕЗ ПРАВИЛА\n"
)


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _block_network(monkeypatch, block_dns: bool = True) -> list[str]:
    """Запрет outbound: любые соединения, кроме loopback (его использует asyncio self-pipe).

    Возвращает список попыток (host) — для проверки, что приложение ходит только туда,
    куда разрешено конфигом.
    """
    attempts: list[str] = []

    def guard(orig):
        def wrapper(sock, address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) else address
            attempts.append(str(host))
            if host not in _LOOPBACK:
                raise AssertionError(f"outbound-сеть запрещена: {host}")
            return orig(sock, address, *args, **kwargs)
        return wrapper

    monkeypatch.setattr(socket.socket, "connect", guard(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(socket.socket.connect_ex))
    if block_dns:  # TestClient резолвит «testserver» — там DNS не блокируем
        orig_gai = socket.getaddrinfo

        def gai_guard(host, *args, **kwargs):
            attempts.append(str(host))
            if host not in _LOOPBACK and host not in (None, ""):
                raise AssertionError(f"DNS-резолв запрещён: {host}")
            return orig_gai(host, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", gai_guard)
    for var in ("SPENDTRACK_FREEL_LLM_API_KEY", "SPENDTRACK_OPENROUTER_API_KEY",
                "SPENDTRACK_ALLOW_LOCAL_LLM"):
        monkeypatch.delenv(var, raising=False)
    return attempts


def test_import_without_llm_goes_to_queue_not_network(monkeypatch, tmp_path):
    """Неизвестный мерчант при выключенном LLM: очередь подтверждения, а не сетевой вызов."""
    _block_network(monkeypatch)
    store = Store(db_path=tmp_path / "offline.db")
    try:
        res = import_csv(UNKNOWN_MERCHANT_CSV, store)
        assert res["added"] == 1
        assert store.pending_count() == 1  # LLM выключен → человеку, без отправки данных
    finally:
        store.close()


def test_reports_and_doctor_offline(monkeypatch, tmp_path):
    """Дайджест/рекурринги/doctor работают без сети (offline-first контур)."""
    _block_network(monkeypatch)
    db = tmp_path / "offline.db"
    store = Store(db_path=db)
    try:
        import_csv(UNKNOWN_MERCHANT_CSV, store)
        from spendtrack.digest import build_digest
        from spendtrack.recurring import detect_recurring

        digest = build_digest(store)  # окно — реальные последние 7 дней; факт сборки и есть проверка
        assert digest["period"]["days"] == 7
        assert store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 1
        assert detect_recurring(store) == []
    finally:
        store.close()

    from spendtrack.doctor import run_checks

    report = run_checks(db)
    assert report["status"] in ("ok", "warn", "info")


def test_byo_cloud_with_dead_network_goes_to_queue(monkeypatch, tmp_path):
    """BYO-провайдер недоступен → строка в очередь; попытки только к BYO-хосту, не к free-каналам."""
    attempts = _block_network(monkeypatch)
    monkeypatch.setenv("SPENDTRACK_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("SPENDTRACK_LLM_MODEL", "byo-model")
    monkeypatch.setenv("SPENDTRACK_LLM_API_KEY", "sk-test")
    store = Store(db_path=tmp_path / "byo.db")
    try:
        res = import_csv(UNKNOWN_MERCHANT_CSV, store)
        assert res["added"] == 1
        assert store.pending_count() == 1
    finally:
        store.close()
    assert attempts, "ожидалась попытка соединения с BYO-эндпоинтом"
    assert all("llm.example.test" in host for host in attempts)


def test_dashboard_renders_offline(monkeypatch, tmp_path):
    """HTTP-страница рендерится in-process при заблокированных соединениях.

    block_dns=False — осознанно: TestClient живёт in-process (ASGI), но резолвит хост «testserver»;
    сами соединения по-прежнему запрещены вне loopback (там их нет).
    """
    _block_network(monkeypatch, block_dns=False)
    db = tmp_path / "offline.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    store = Store(db_path=db)
    try:
        import_csv(UNKNOWN_MERCHANT_CSV, store)
    finally:
        store.close()

    from fastapi.testclient import TestClient

    from spendtrack.main import app

    with TestClient(app) as client:
        assert client.get("/dashboard").status_code == 200
        assert client.get("/approve").status_code == 200
