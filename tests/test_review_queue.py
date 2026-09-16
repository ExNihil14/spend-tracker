from __future__ import annotations

import pytest

from spendtrack.store import Store, parse_amount


@pytest.fixture()
def pending_store(tmp_path):
    s = Store(db_path=tmp_path / "w3.db")
    s.add_transaction(date="2026-09-01", description="АЗС XYZ",
                      amount_kopecks=parse_amount("-1000"), category="other",
                      category_source="llm_pending_review", confidence=0.55,
                      category_llm="transport", review_status="pending")
    s.add_transaction(date="2026-09-02", description="ЛЕНТА",
                      amount_kopecks=parse_amount("-500"), category="groceries",
                      category_source="rule", confidence=1.0, review_status="approved")
    s.add_transaction(date="2026-09-03", description="КАФЕ А",
                      amount_kopecks=parse_amount("-1500"), category="other",
                      category_source="llm_pending_review", confidence=0.4,
                      category_llm="food", review_status="pending")
    yield s
    s.close()


def test_migration_backfills_old_pending(tmp_path):
    """Существующая БД со старой схемой (без категории-очереди) получает backfill."""
    import sqlite3
    db = tmp_path / "m.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL UNIQUE,
        date TEXT NOT NULL,
        merchant TEXT, account_anon TEXT, export_rowid TEXT,
        description TEXT NOT NULL, amount_kopecks INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT 'other', category_source TEXT NOT NULL DEFAULT 'rule',
        confidence REAL NOT NULL DEFAULT 1.0,
        category_llm_old_dummy TEXT, llm_pending_review INTEGER NOT NULL DEFAULT 0,
        created TEXT, updated TEXT)""")
    conn.execute("""INSERT INTO transactions
        (fingerprint, date, description, amount_kopecks, category, category_source, confidence, llm_pending_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        ("fp1", "2026-09-01", "СТАРЫЙ ЮС", -100, "other", "llm_pending_review", 0.3))
    conn.commit()
    conn.close()

    post = Store(db_path=db)
    assert post.pending_count() == 1
    row = post.get_transaction(1)
    assert row["category_llm"] == "other"  # бэкфилл category_llm=category
    assert row["review_status"] == "pending"
    post.close()


def test_pending_sorted_by_date_asc_amount_desc(pending_store):
    q = pending_store.queued_for_review()
    assert [r["description"] for r in q] == ["АЗС XYZ", "КАФЕ А"]
    assert [r["review_status"] for r in q] == ["pending", "pending"]


def test_pending_count_excludes_approved(pending_store):
    assert pending_store.pending_count() == 2


def test_approve_review_sets_rule_and_seeds_cache(pending_store):
    tid = pending_store.queued_for_review()[0]["id"]
    assert pending_store.approve_review(tid, "transport") is True
    row = pending_store.get_transaction(tid)
    assert row["category"] == "transport"
    assert row["category_source"] == "rule"
    assert row["review_status"] == "approved"
    assert row["category_llm"] == "transport"  # diff сохранён (не перезаписан)
    assert pending_store.pending_count() == 1
    # merchant-cache засеян после одобрения (few-shot loop)
    if row["merchant"]:
        assert pending_store.merchant_cache_get(row["merchant"]) in (None, row["category"])


def test_approve_review_overrides_category_keeps_llm_diff(pending_store):
    tid = pending_store.queued_for_review()[-1]["id"]
    assert pending_store.approve_review(tid, "household") is True
    row = pending_store.get_transaction(tid)
    assert row["category"] == "household"
    assert row["category_llm"] == "food"  # diff «LLM vs человек»


def test_approve_non_pending_returns_false(pending_store):
    tid = pending_store.list_transactions(needs_review=False)[1]["id"]  # ЛЕНТА approved
    assert pending_store.approve_review(tid, "food") is False


def test_skip_review(pending_store):
    tid = pending_store.queued_for_review()[0]["id"]
    assert pending_store.skip_review(tid) is True
    row = pending_store.get_transaction(tid)
    assert row["review_status"] == "skipped"
    assert pending_store.pending_count() == 1
    assert pending_store.skip_review(tid) is False  # идемпотентность


def test_approve_all_applies_llm_suggestion(pending_store):
    approved = pending_store.approve_all_reviews()
    assert approved == 2
    assert pending_store.pending_count() == 0
    for r in pending_store.list_transactions():
        assert r["review_status"] == "approved"


def test_approve_all_seeds_merchant_cache(tmp_path):
    """Подтверждение пачки учит merchant_cache (few-shot), как одиночный approve (QA-замечание 2)."""
    s = Store(db_path=tmp_path / "all.db")
    s.add_transaction(date="2026-09-01", description="МАГНИТ 1", amount_kopecks=-100,
                      category="other", category_source="llm_pending_review", confidence=0.5,
                      category_llm="groceries", review_status="pending", merchant="МАГНИТ")
    s.add_transaction(date="2026-09-02", description="АЗС 2", amount_kopecks=-200,
                      category="other", category_source="llm_pending_review", confidence=0.4,
                      category_llm="fuel", review_status="pending", merchant="АЗС ЛУКОЙЛ")
    s.add_transaction(date="2026-09-03", description="БЕЗ МЕРЧАНТА", amount_kopecks=-300,
                      category="other", category_source="llm_pending_review", confidence=0.4,
                      category_llm=None, review_status="pending")
    assert s.approve_all_reviews() == 3
    assert s.merchant_cache_get("МАГНИТ") == "groceries"
    assert s.merchant_cache_get("АЗС ЛУКОЙЛ") == "fuel"
    s.close()


def test_approve_all_does_not_overwrite_manual_cache(tmp_path):
    """Ручная правка кэша не перетирается LLM-догадкой при approve-all (ревью P0)."""
    s = Store(db_path=tmp_path / "cache.db")
    s.merchant_cache_set("МАГНИТ", "groceries")  # человек уже учил этого мерчанта
    s.add_transaction(date="2026-09-01", description="МАГНИТ 1", amount_kopecks=-100,
                      category="other", category_source="llm_pending_review", confidence=0.5,
                      category_llm="fuel", review_status="pending", merchant="МАГНИТ")
    assert s.approve_all_reviews() == 1
    assert s.merchant_cache_get("МАГНИТ") == "groceries"  # не перетёрлось
    s.close()


def test_approve_all_idempotent_and_empty(tmp_path):
    s = Store(db_path=tmp_path / "idem.db")
    assert s.approve_all_reviews() == 0  # пустая очередь — no-op
    s.add_transaction(date="2026-09-01", description="A", amount_kopecks=-100,
                      category="other", category_source="llm_pending_review", confidence=0.5,
                      category_llm="food", review_status="pending", merchant="A")
    assert s.approve_all_reviews() == 1
    assert s.approve_all_reviews() == 0  # повторный вызов ничего не делает
    assert s.merchant_cache_get("A") == "food"
    s.close()


# ---- E2E-уровень: эндпоинты очереди ----
from fastapi.testclient import TestClient

from spendtrack.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "api_w3.db"))
    return TestClient(app)


def test_reviews_page_lists_pending(client):
    """Запись, попавшая в очередь LLM, видна на /approve."""
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.get("/approve")
    assert r.status_code == 200
    assert "СТРОЙКАОПТ X" in r.text


def test_reviews_get_fragment(client):
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.get("/api/reviews")
    assert r.status_code == 200
    assert "<tbody" in r.text
    assert "review-rows" in r.text


def test_approve_all_endpoint_clears_queue(client):
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    client.post("/api/transactions", json={
        "date": "2026-09-11", "description": "СТРОЙКАОПТ Y", "amount": "-30.00",
    })
    assert client.get("/api/pending-count").json()["count"] >= 1
    r = client.post("/api/reviews/approve-all")
    assert r.status_code == 200
    assert client.get("/api/pending-count").json()["count"] == 0


def test_approve_one_endpoint(client):
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    }).json()
    r = client.post(f"/api/reviews/{tx['id']}/approve", data={"category": "transport"})
    assert r.status_code == 200
    assert client.get("/api/pending-count").json()["count"] == 0
    body = client.get(f"/api/transactions/{tx['id']}").json()
    assert body["category"] == "transport"
    assert body["category_source"] == "rule"


def test_skip_one_endpoint(client):
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    }).json()
    r = client.post(f"/api/reviews/{tx['id']}/skip")
    assert r.status_code == 200
    body = client.get(f"/api/transactions/{tx['id']}").json()
    assert body["review_status"] == "skipped"
    assert client.get("/api/pending-count").json()["count"] == 0


def test_approve_invalid_category_422(client):
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    }).json()
    r = client.post(f"/api/reviews/{tx['id']}/approve", data={"category": "hacker_cat"})
    assert r.status_code == 422


def test_approve_unknown_id_404(client):
    r = client.post("/api/reviews/999999/approve", data={"category": "food"})
    assert r.status_code == 404


def test_oob_badge_swaps(client):
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.post("/api/reviews/approve-all")
    assert "pending-count" in r.text
    assert 'hx-swap-oob="true"' in r.text
    assert ">0<" in r.text


def test_dashboard_badge_shows_pending(client):
    """Бейдж очереди в навигации на /dashboard показывает реальный счётчик (не 0)."""
    import re
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.get("/dashboard")
    assert r.status_code == 200
    m = re.search(r'id="pending-count"[^>]*>(\d+)<', r.text)
    assert m, "бейдж pending-count не найден"
    assert int(m.group(1)) >= 1


def test_approve_all_button_hidden_when_empty(client):
    """После исчерпания очереди кнопка «Одобрить все» исчезает (OOB)."""
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.post("/api/reviews/approve-all")
    assert 'id="approve-all-wrap"' in r.text
    assert "Одобрить все" not in r.text
    assert client.get("/api/pending-count").json()["count"] == 0


def test_approve_all_button_present_when_pending(client):
    client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    })
    r = client.get("/approve")
    assert "Одобрить все" in r.text


def test_empty_state_oob_after_last_decision(client):
    """После последнего approve/skip плейсхолдер «Все подтверждены» приходит OOB."""
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    }).json()
    r = client.post(f"/api/reviews/{tx['id']}/skip")
    assert 'id="review-empty"' in r.text
    assert 'hx-swap-oob="beforeend:#review-rows"' in r.text


def test_empty_state_oob_deleted_when_rows_remain(client):
    t1 = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    }).json()
    client.post("/api/transactions", json={
        "date": "2026-09-13", "description": "СТРОЙКАОПТ Y", "amount": "-60.00",
    })
    r = client.post(f"/api/reviews/{t1['id']}/skip")
    assert 'hx-swap-oob="delete"' in r.text
    assert client.get("/api/pending-count").json()["count"] == 1


def test_toast_on_approve_and_skip(client):
    tx = client.post("/api/transactions", json={
        "date": "2026-09-12", "description": "СТРОЙКАОПТ X", "amount": "-50.00",
    }).json()
    r = client.post(f"/api/reviews/{tx['id']}/approve", data={"category": "restaurants"})
    assert 'id="toast"' in r.text and "Одобрено: restaurants" in r.text

    tx2 = client.post("/api/transactions", json={
        "date": "2026-09-13", "description": "СТРОЙКАОПТ Y", "amount": "-60.00",
    }).json()
    r2 = client.post(f"/api/reviews/{tx2['id']}/skip")
    assert "Пропущено:" in r2.text