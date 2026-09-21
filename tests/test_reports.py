from __future__ import annotations

import pytest

from spendtrack.reports import (
    categories_with_totals,
    confidence_calibration,
    report_daily,
    report_month,
    wilson_interval,
)
from spendtrack.store import parse_amount


def _populate(store):
    store.add_transaction("2026-09-01", "ЛЕНТА", parse_amount("-1234.50"), "groceries", "rule", merchant="ЛЕНТА")
    store.add_transaction("2026-09-02", "UBER", parse_amount("-1200"), "transport", "rule", merchant="UBER")
    store.add_transaction("2026-09-03", "Зарплата", parse_amount("250000"), "income", "rule", merchant="ZP")
    store.add_transaction("2026-09-04", "NETFLIX", parse_amount("-1549"), "subscriptions", "rule", merchant="NETFLIX")
    store.add_transaction("2026-10-01", "ОЗОН", parse_amount("-500"), "household", "rule")


def test_report_month_summary(store):
    _populate(store)
    rep = report_month(store, "2026-09")
    assert rep["income_k"] == 250000 * 100       # 250000 руб = 25 000 000 коп
    assert rep["expense_k"] == -123450 - 120000 - 154900  # -398350 коп


def test_report_month_excludes_other_months(store):
    _populate(store)
    rep = report_month(store, "2026-09")
    cats = {c["category"]: c for c in rep["categories"]}
    assert "household" not in cats


def test_categories_layout(store):
    _populate(store)
    totals = categories_with_totals(store, "2026-09")
    names = [c["category"] for c in totals]
    assert names == sorted(names)


def test_empty_db(store):
    rep = report_month(store, "2026-09")
    assert rep["income_k"] == 0
    assert rep["expense_k"] == 0
    assert rep["categories"] == []


def test_report_daily_series(store):
    _populate(store)
    series = report_daily(store, "2026-09")
    by_date = {d["date"]: d for d in series}
    assert by_date["2026-09-01"]["total_k"] == -123450
    assert "2026-10-01" not in by_date
    assert all(d["date"] >= "2026-09-01" and d["date"] <= "2026-09-30" for d in series)


def test_report_daily_empty(store):
    assert report_daily(store, "2026-09") == []


# ── калибровка порога авто-приёма ───────────────────────────────────────────


def _seed_llm(store, day: int, conf: float, proposed: str, final: str, status: str = "approved",
              month: int = 9):
    store.add_transaction(
        date=f"2026-{month:02d}-{day:02d}", description=f"TX{month}-{day}", amount_kopecks=-100,
        category=final, category_source="llm" if final == proposed else "correction",
        confidence=conf, category_llm=proposed, review_status=status, merchant=f"M{month}-{day}")


def test_confidence_calibration(store):
    _seed_llm(store, 1, 0.95, "groceries", "groceries")   # 0.9: согласие
    _seed_llm(store, 2, 0.92, "groceries", "other")       # 0.9: исправлено человеком
    _seed_llm(store, 3, 0.55, "transport", "transport")   # 0.5: согласие
    _seed_llm(store, 4, 0.54, "food", "groceries")        # 0.5: исправлено
    _seed_llm(store, 5, 0.35, "household", "household", status="pending")
    _seed_llm(store, 6, 0.65, "subscriptions", "subscriptions", status="skipped")

    rep = confidence_calibration(store, current_threshold=0.9)
    assert (rep["total"], rep["resolved"], rep["pending"], rep["skipped"]) == (6, 4, 1, 1)
    assert rep["low_data"] is True
    b = {x["bucket"]: x for x in rep["buckets"]}
    assert b["0.9"] == {"bucket": "0.9", "n": 2, "agreed": 1, "corrected": 1, "wrong_rate": 0.5}
    assert b["0.5"]["n"] == 2 and b["0.5"]["corrected"] == 1
    assert "0.3" not in b and "0.6" not in b  # pending/skipped не создают бакеты
    t = {x["threshold"]: x for x in rep["thresholds"]}
    assert t[0.9]["accepted"] == 2 and t[0.9]["corrected"] == 1 and t[0.9]["coverage"] == 0.5
    assert t[0.5]["accepted"] == 4 and t[0.5]["wrong_rate"] == 0.5
    assert rep["current_threshold"] == 0.9
    assert rep["recommendation"]["status"] == "low_data"
    assert rep["recommendation"]["threshold"] is None


def test_wilson_interval_known_values():
    """Сверка с табличными значениями Wilson 95% (z=1.96)."""
    low, high = wilson_interval(5, 100)
    assert abs(low - 0.0215) < 0.003 and abs(high - 0.1118) < 0.003
    low0, high0 = wilson_interval(0, 10)
    assert low0 == 0.0 and abs(high0 - 0.2775) < 0.005
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low_all, high_all = wilson_interval(10, 10)
    assert high_all == 1.0 and low_all > 0.6
    # больше данных при нуле ошибок → верхняя граница строго ниже
    assert wilson_interval(0, 40)[1] < wilson_interval(0, 10)[1]
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)
    with pytest.raises(ValueError):
        wilson_interval(5, 4)


def test_confidence_recommendation_respects_params(store):
    """target_error/min_sample — параметры: с мягкой целью и малой выборкой порог находится сразу."""
    for day in range(1, 6):
        _seed_llm(store, day, 0.95, "groceries", "groceries")
    rep = confidence_calibration(store, target_error=0.5, min_sample=5)
    assert rep["recommendation"]["status"] == "ok"
    assert rep["recommendation"]["threshold"] == 0.4
    assert rep["recommendation"]["target_error"] == 0.5
    assert rep["recommendation"]["min_sample"] == 5


def test_confidence_recommendation_with_enough_data(store):
    """40 безошибочных решений на 0.95 + 5 спорных на 0.5 → безопасный порог 0.6 (макс. покрытие)."""
    for month, day in [(7, d) for d in range(1, 21)] + [(8, d) for d in range(1, 21)]:
        _seed_llm(store, day, 0.95, "groceries", "groceries", month=month)
    for day in range(1, 6):
        _seed_llm(store, day, 0.5, "transport", "transport" if day % 2 == 0 else "other")
    rep = confidence_calibration(store, current_threshold=0.9)
    assert rep["recommendation"]["status"] == "ok"
    assert rep["recommendation"]["threshold"] == 0.6
    t = {x["threshold"]: x for x in rep["thresholds"]}
    assert t[0.5]["wrong_high"] > rep["recommendation"]["target_error"]
    assert t[0.6]["wrong_high"] <= rep["recommendation"]["target_error"]


def test_confidence_recommendation_no_candidate_when_errors(store):
    """Даже при достаточной выборке порог не рекомендуется, если ошибки есть на всех уровнях."""
    for month, day in [(7, d) for d in range(1, 21)] + [(8, d) for d in range(1, 6)]:
        _seed_llm(store, day, 0.95, "groceries", "other", month=month)
    rep = confidence_calibration(store)
    assert rep["recommendation"]["status"] == "no_candidate"
    assert rep["recommendation"]["threshold"] is None


def test_confidence_calibration_ignores_empty_proposal(store):
    _seed_llm(store, 1, 0.95, "groceries", "groceries")
    store.add_transaction(date="2026-09-02", description="TXE", amount_kopecks=-100,
                          category="other", category_source="llm", confidence=0.9,
                          category_llm="")
    rep = confidence_calibration(store)
    assert rep["total"] == 1  # пустое предложение LLM не искажает выборку


def test_confidence_calibration_bucket_1_0_first(store):
    _seed_llm(store, 1, 1.0, "groceries", "groceries")
    _seed_llm(store, 2, 0.5, "transport", "transport")
    rep = confidence_calibration(store)
    assert [b["bucket"] for b in rep["buckets"]] == ["1.0", "0.5"]


def test_confidence_calibration_empty(store):
    rep = confidence_calibration(store)
    assert rep["total"] == 0 and rep["buckets"] == [] and rep["low_data"] is True
    assert all(t["coverage"] == 0.0 and t["wrong_rate"] == 0.0 for t in rep["thresholds"])


def test_cli_confidence_command(store, tmp_path, monkeypatch, capsys):
    _seed_llm(store, 1, 0.95, "groceries", "groceries")
    store.close()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "test.db"))
    from spendtrack import cli
    assert cli.main(["confidence"]) == 0
    out = capsys.readouterr().out
    assert "Калибровка порога" in out and "Текущий порог" in out and "t=0.9" in out
    assert "рекомендация:" in out  # #11: рекомендация порога по Wilson-CI (здесь — «данных мало»)