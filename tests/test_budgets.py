from __future__ import annotations

import pytest

from spendtrack.reports import budgets_progress


def test_budget_set_clear_roundtrip(store):
    store.set_budget("groceries", 20000_00)
    assert store.budget_map() == {"groceries": 2_000_000}
    store.set_budget("groceries", 30000_00)  # upsert
    assert store.budget_map() == {"groceries": 3_000_000}
    store.clear_budget("groceries")
    assert store.budget_map() == {}


def test_budget_rejects_nonpositive(store):
    with pytest.raises(ValueError):
        store.set_budget("groceries", 0)
    with pytest.raises(ValueError):
        store.set_budget("groceries", -100)


def test_budgets_progress_sign_month_and_over(store):
    store.set_budget("groceries", 2000_00)
    store.set_budget("transport", 1000_00)
    store.add_transaction("2026-09-01", "ЛЕНТА", -1500_00, "groceries", "rule")
    store.add_transaction("2026-09-02", "ВОЗВРАТ", 300_00, "groceries", "rule")   # возврат уменьшает расход
    store.add_transaction("2026-09-03", "ТАКСИ", -1200_00, "transport", "rule")   # перерасход
    store.add_transaction("2026-10-01", "ЛЕНТА", -999_00, "groceries", "rule")    # другой месяц

    items = {b["category"]: b for b in budgets_progress(store, "2026-09")}
    g = items["groceries"]
    assert (g["spent_k"], g["budget_k"], g["pct"], g["over"]) == (1200_00, 2000_00, 60.0, False)
    t = items["transport"]
    assert t["over"] is True and t["over_k"] == 200_00 and t["remaining_k"] == -200_00
    assert t["pct"] == 120.0


def test_budgets_progress_refund_beyond_spent(store):
    store.set_budget("groceries", 1000_00)
    store.add_transaction("2026-09-01", "ВОЗВРАТ", 500_00, "groceries", "rule")
    b = budgets_progress(store, "2026-09")[0]
    assert b["spent_k"] == -500_00 and b["pct"] == 0.0 and b["over"] is False
    assert b["remaining_k"] == 1000_00  # возвраты не увеличивают остаток сверх бюджета


def test_budgets_progress_thresholds(store):
    store.set_budget("groceries", 1000_00)
    store.add_transaction("2026-09-01", "ЛЕНТА", -1000_00, "groceries", "rule")
    b = budgets_progress(store, "2026-09")[0]
    assert (b["pct"], b["over"]) == (100.0, False)  # ровно в бюджет — ещё не перерасход

    store.add_transaction("2026-09-02", "ЛЕНТА", -1, "groceries", "rule")  # +1 копейка
    b2 = budgets_progress(store, "2026-09")[0]
    assert b2["over"] is True and b2["over_k"] == 1 and b2["remaining_k"] == -1


def test_budgets_progress_excluded_and_known(store):
    store.set_budget("income", 50000_00)  # не бюджетируется, но в БД быть может
    store.set_budget("groceries", 1000_00)
    assert [b["category"] for b in budgets_progress(store, "2026-09")] == ["groceries"]
    assert budgets_progress(store, "2026-09", known={"transport"}) == []  # удалённую категорию не выводим


def test_budgets_progress_empty(store):
    assert budgets_progress(store, "2026-09") == []


def test_cli_budget_command(store, tmp_path, monkeypatch, capsys):
    store.set_budget("groceries", 1000_00)
    store.add_transaction("2026-09-01", "ЛЕНТА", -250_00, "groceries", "rule")
    store.close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "test.db"))
    from spendtrack import cli
    assert cli.main(["budget", "--month", "2026-09"]) == 0
    out = capsys.readouterr().out
    assert "groceries" in out and "25%" in out


def test_budgets_progress_sorted_by_risk(store):
    """M-5: бюджеты сортируются по риску — перерасход выше «близко к лимиту», а не по алфавиту."""
    store.set_budget("groceries", 1000_00)   # 120% — перерасход
    store.set_budget("transport", 1000_00)   # 90% — близко к лимиту
    store.set_budget("fuel", 1000_00)        # 10% — спокойно
    store.add_transaction("2026-09-01", "ЛЕНТА", -1200_00, "groceries", "rule")
    store.add_transaction("2026-09-02", "ТАКСИ", -900_00, "transport", "rule")
    store.add_transaction("2026-09-03", "АЗС", -100_00, "fuel", "rule")
    assert [b["category"] for b in budgets_progress(store, "2026-09")] == ["groceries", "transport", "fuel"]
