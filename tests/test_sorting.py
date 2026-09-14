from __future__ import annotations

from fastapi.testclient import TestClient

from spendtrack.csv_import import import_csv
from spendtrack.main import app
from spendtrack.store import Store

SBER_CSV = """Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Описание
1;01.09.2026 09:00;1234;Выполнено;-100,00;RUB;ПЕРВАЯ
2;01.09.2026 10:00;1234;Выполнено;-500,00;RUB;ВТОРАЯ
3;01.09.2026 11:00;1234;Выполнено;-50,00;RUB;ТРЕТЬЯ
"""


def _stub(tx, store, taxonomy):
    return {"category": "other", "confidence": 0.5, "merchant": None, "source": "llm_pending_review"}


def test_import_sets_statement_order(tmp_path):
    s = Store(db_path=tmp_path / "t.db")
    import_csv(SBER_CSV, s, classify=_stub)
    rows = s.conn.execute(
        "SELECT description, statement_order FROM transactions ORDER BY statement_order").fetchall()
    assert [r["description"] for r in rows] == ["ПЕРВАЯ", "ВТОРАЯ", "ТРЕТЬЯ"]
    assert [r["statement_order"] for r in rows] == [0, 1, 2]
    s.close()


def test_recent_sort_uses_statement_order_within_day(tmp_path):
    """Внутри дня «новые сверху» = последние строки выписки (statement_order DESC), а не id."""
    s = Store(db_path=tmp_path / "t.db")
    import_csv(SBER_CSV, s, classify=_stub)
    got = [t["description"] for t in s.list_transactions(sort="recent")]
    assert got == ["ТРЕТЬЯ", "ВТОРАЯ", "ПЕРВАЯ"]
    s.close()


def test_amount_sort_by_abs_desc(tmp_path):
    s = Store(db_path=tmp_path / "t.db")
    import_csv(SBER_CSV, s, classify=_stub)
    got = [t["description"] for t in s.list_transactions(sort="amount")]
    assert got == ["ВТОРАЯ", "ПЕРВАЯ", "ТРЕТЬЯ"]  # 500 → 100 → 50
    s.close()


def test_manual_rows_fall_back_to_id(tmp_path):
    s = Store(db_path=tmp_path / "t.db")
    s.add_transaction(date="2026-09-01", description="MANUAL", amount_kopecks=-100,
                      category="other", category_source="manual")
    rows = s.list_transactions(sort="recent")
    assert rows[0]["description"] == "MANUAL"
    s.close()


def test_index_sort_param_renders_amount_order(tmp_path, monkeypatch):
    """URL-параметр sort=amount отражается в порядке строк (детерминированно, без LLM)."""
    db = tmp_path / "api.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    s = Store(db_path=db)
    for desc, amount in (("МАЛАЯ", -1000), ("КРУПНАЯ", -90000), ("СРЕДНЯЯ", -5000)):
        s.add_transaction(date="2026-09-12", description=desc, amount_kopecks=amount,
                          category="other", category_source="manual")
    s.close()

    client = TestClient(app)
    html = client.get("/?sort=amount&month=2026-09").text
    assert html.index("КРУПНАЯ") < html.index("СРЕДНЯЯ") < html.index("МАЛАЯ")
