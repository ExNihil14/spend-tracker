"""Конкурентный HTTP-смоук (§G-5): параллельные чтения/запись без 500 и `database is locked`."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.store import Store


def test_parallel_reads_and_writes(tmp_path, monkeypatch):
    """6 потоков одновременно пишут транзакции и читают страницы — все 200, строки на месте."""
    db = tmp_path / "http.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))

    def worker(i: int) -> tuple[int, int, int]:
        client = TestClient(app)  # свой клиент на поток: транспорт не шарим между потоками
        created = client.post("/api/transactions", json={
            "date": "2026-09-12", "description": f"ТОВАР {i}", "amount": "-100.00"})
        page = client.get("/")
        count = client.get("/api/reviews/count")
        return created.status_code, page.status_code, count.status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(worker, range(6)))

    assert all(c == 200 and p == 200 and n == 200 for c, p, n in results)
    store = Store(db_path=db)
    try:
        assert store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 6
    finally:
        store.close()
