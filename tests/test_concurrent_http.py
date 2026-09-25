"""Конкурентный HTTP-смоук (§G-5): параллельные чтения/запись без 500 и `database is locked`."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.store import Store


def test_parallel_reads_and_writes(tmp_path, monkeypatch):
    """4 потока одновременно пишут транзакции и читают страницы — все 200, строки на месте.

    Схему создаём заранее: иначе потоки наперегонки прогоняют миграции на свежей БД (флейк полного
    прогона 25.09). Корневое лечение — fast-path `Store.__init__` по `user_version` (тикет K7).
    """
    db = tmp_path / "http.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    Store(db_path=db).close()  # схема+миграции один раз до потоков

    def worker(i: int) -> tuple[int, int, int]:
        client = TestClient(app)  # свой клиент на поток: транспорт не шарим между потоками
        created = client.post("/api/transactions", json={
            "date": "2026-09-12", "description": f"ТОВАР {i}", "amount": "-100.00"})
        page = client.get("/")
        count = client.get("/api/reviews/count")
        return created.status_code, page.status_code, count.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))

    assert all(c == 200 and p == 200 and n == 200 for c, p, n in results)
    store = Store(db_path=db)
    try:
        assert store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 4
    finally:
        store.close()
