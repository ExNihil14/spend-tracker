from __future__ import annotations

import re

from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.store import Store

DATES = ("2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09")


def _seed(s: Store) -> None:
    for d in DATES:
        for i in range(2):
            s.add_transaction(date=d, description=f"{d}-{i}", amount_kopecks=-(1000 + i),
                              category="other", category_source="manual")


def test_days_pagination_no_split(tmp_path):
    """Keyset по дням: страницы содержат целые дни, без пересечений, с корректным has_more."""
    s = Store(db_path=tmp_path / "t.db")
    _seed(s)

    page1, after1, more1 = s.list_transactions_days(month="2026-09", days=2)
    assert more1 is True
    assert {t["date"] for t in page1} == {"2026-09-09", "2026-09-08"}
    assert len(page1) == 4  # целые дни (по 2 строки), день не разрезан

    page2, after2, more2 = s.list_transactions_days(month="2026-09", days=2, after_date=after1)
    assert {t["date"] for t in page2} == {"2026-09-07", "2026-09-06"}
    assert more2 is True

    page3, _after3, more3 = s.list_transactions_days(month="2026-09", days=2, after_date=after2)
    assert {t["date"] for t in page3} == {"2026-09-05"}
    assert more3 is False
    s.close()


def test_more_endpoint_rows_and_sentinel(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    s = Store(db_path=db)
    _seed(s)
    s.close()

    client = TestClient(app)

    # после 2026-09-07 остаются 2 дня → страница полная, sentinel не нужен
    html = client.get("/transactions/more?month=2026-09&days=2&after=2026-09-07").text
    assert "2026-09-06" in html and "2026-09-05" in html
    assert "итог" in html
    assert "more-sentinel" not in html

    # после 2026-09-09 остаётся 4 дня при странице в 2 дня → sentinel есть
    html2 = client.get("/transactions/more?month=2026-09&days=2&after=2026-09-09").text
    assert "more-sentinel" in html2
    assert "after=2026-09-07" in html2  # курсор следующей страницы
    # кнопка-фолбэк (клавиатура/инерционный скролл), а не только hx-trigger="revealed"
    assert "Показать ещё" in html2
    sentinel = re.search(r'id="more-sentinel"[^>]*hx-trigger="([^"]*)"', html2)
    assert sentinel is not None
    triggers = {t.strip() for t in sentinel.group(1).split(",")}
    assert triggers == {"revealed", "click"}


def test_days_pagination_applies_category_and_search(tmp_path):
    """Регресс (смоук 23.09): фильтры применяются и к строкам страницы, не только к выбору дней.

    Было: дни выбирались по условию, а строки — `WHERE date IN (...)` без фильтров →
    в таблицу протекали все операции этих дней (категория/поиск не работали в «recent»).
    """
    s = Store(db_path=tmp_path / "f.db")
    s.add_transaction(date="2026-09-10", description="ЛЕНТА", amount_kopecks=-1000,
                      category="groceries", category_source="manual")
    s.add_transaction(date="2026-09-10", description="ТАКСИ", amount_kopecks=-2000,
                      category="transport", category_source="manual")
    s.add_transaction(date="2026-09-11", description="ПЯТЁРОЧКА", amount_kopecks=-3000,
                      category="groceries", category_source="manual")

    only_groceries, _, _ = s.list_transactions_days(month="2026-09", category="groceries")
    assert {t["description"] for t in only_groceries} == {"ЛЕНТА", "ПЯТЁРОЧКА"}

    only_taxi, _, _ = s.list_transactions_days(month="2026-09", search="ТАКСИ")
    assert [t["description"] for t in only_taxi] == ["ТАКСИ"]
    s.close()


def test_index_category_filter_no_leak(tmp_path, monkeypatch):
    """Регресс UI: ?category= не показывает чужие операции того же дня."""
    db = tmp_path / "leak.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    s = Store(db_path=db)
    s.add_transaction(date="2026-09-10", description="ЛЕНТА ФИЛЬТР", amount_kopecks=-1000,
                      category="groceries", category_source="manual")
    s.add_transaction(date="2026-09-10", description="ТАКСИ ФИЛЬТР", amount_kopecks=-2000,
                      category="transport", category_source="manual")
    s.close()

    html = TestClient(app).get("/?month=2026-09&category=groceries").text
    assert "ЛЕНТА ФИЛЬТР" in html
    assert "ТАКСИ ФИЛЬТР" not in html


def test_index_month_fits_one_page(tmp_path, monkeypatch):
    db = tmp_path / "idx.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    s = Store(db_path=db)
    _seed(s)
    s.close()

    html = TestClient(app).get("/?month=2026-09").text
    assert "more-sentinel" not in html  # 5 дней < 31 → всё на одной странице
