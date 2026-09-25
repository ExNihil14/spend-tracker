"""CLI add: результат классификатора сохраняется целиком — очередь/предложение LLM не теряются."""
from __future__ import annotations

from spendtrack import cli
from spendtrack.store import Store

PENDING = {"category": "other", "source": "llm_pending_review", "confidence": 0.5,
           "category_llm": "other", "review_status": "pending", "merchant": "TEST", "reason": "r"}
ACCEPTED = {"category": "restaurants", "source": "llm", "confidence": 0.98,
            "category_llm": "restaurants", "review_status": "approved", "merchant": "DODO"}


def _run_add(monkeypatch, tmp_path, result=None, category=None, classify=None):
    db = tmp_path / "cli_add.db"
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(db))
    calls: list[dict] = []

    if classify is None:
        def classify(tx, taxonomy, store):
            calls.append(tx)
            return result

    monkeypatch.setattr(cli, "categorize_transaction", classify)
    argv = ["add", "-123.45", "ТЕСТОВЫЙ МЕРЧАНТ"]
    if category:
        argv += ["--category", category]
    rc = cli.main(argv)
    store = Store(db_path=db)
    row = store.conn.execute(
        "SELECT category, category_source, confidence, category_llm, review_status FROM transactions"
    ).fetchone()
    store.close()
    return rc, (dict(row) if row else None), calls


def test_add_persists_pending_llm_suggestion(monkeypatch, tmp_path):
    """Низкая уверенность LLM → pending + category_llm сохраняются (строка в очереди)."""
    rc, row, calls = _run_add(monkeypatch, tmp_path, result=PENDING)
    assert rc == 0
    assert len(calls) == 1
    assert row["category_source"] == "llm_pending_review"
    assert row["review_status"] == "pending"
    assert row["category_llm"] == "other"
    assert row["confidence"] == 0.5


def test_add_persists_accepted_llm_result(monkeypatch, tmp_path):
    """Высокая уверенность → source=llm, confidence сохраняется (калибровка не слепнет)."""
    rc, row, _ = _run_add(monkeypatch, tmp_path, result=ACCEPTED)
    assert rc == 0
    assert row["category"] == "restaurants"
    assert row["category_source"] == "llm"
    assert row["review_status"] == "approved"
    assert row["confidence"] == 0.98


def test_add_invalid_amount_is_friendly_error(tmp_path, monkeypatch, capsys):
    """Опечатка/не-число в сумме — понятная ошибка (exit 1), а не трейсбек (property-тесты §G)."""
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "bad.db"))
    for bad in ("abc", "nan"):
        assert cli.main(["add", bad, "ТЕСТ"]) == 1
        err = capsys.readouterr().err
        assert "не разобрана сумма" in err and bad in err


def test_add_explicit_category_skips_llm(monkeypatch, tmp_path):
    """--category — ручной ввод: классификатор не вызывается, source=manual."""
    def explode(*args, **kwargs):
        raise AssertionError("классификатор не должен вызываться при --category")

    rc, row, _ = _run_add(monkeypatch, tmp_path, classify=explode, category="groceries")
    assert rc == 0
    assert row["category"] == "groceries"
    assert row["category_source"] == "manual"
    assert row["review_status"] == "approved"
    assert row["category_llm"] is None
