from __future__ import annotations

import importlib.util
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bench():
    spec = importlib.util.spec_from_file_location("bench_script", ROOT / "scripts" / "bench.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, code: int, text: str = ""):
        self.status_code = code
        self.text = text


class _Client:
    def __init__(self, code: int, text: str):
        self.code, self.text = code, text
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, **kw):
        self.calls.append((path, kw))
        return _Resp(self.code, self.text)


def test_seed_calendar_months_and_actual_pending(tmp_path, monkeypatch):
    """B-17 spend_tail #4/#8: календарные месяцы (без дублей/пропусков) и ЧЕСТНЫЕ facts.

    Красная сторона (адъюдикация, проба D): «+30 дней → .replace(day=1)» давал две записи
    NETFLIX в январе и НИ ОДНОЙ в феврале; pending в facts был константой 200.
    """
    bench = _bench()

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(bench, "datetime", FakeDT)
    db = tmp_path / "b.db"
    facts = bench.seed(db, n=0, months=2)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    netflix = [r["date"] for r in con.execute(
        "SELECT date FROM transactions WHERE merchant='NETFLIX' ORDER BY date")]
    salary = [r["date"] for r in con.execute(
        "SELECT date FROM transactions WHERE description='ЗАРАБОТНАЯ ПЛАТА' ORDER BY date")]
    pending = con.execute("SELECT COUNT(1) FROM transactions WHERE review_status='pending'"
                          ).fetchone()[0]
    con.close()
    assert netflix == ["2026-01-05", "2026-02-05"], f"подписки не по календарным месяцам: {netflix}"
    assert len(salary) == 4 and len(set(salary)) == 4, f"зарплаты с дублями: {salary}"
    assert facts["n_transactions"] == 16
    assert facts["pending"] == pending == 16, f"facts.pending должен считаться из данных: {facts}"
    assert facts["warning"], "n=0 меньше обязательного набора — facts обязаны предупредить"


def test_import_case_requires_added_match(monkeypatch):
    """B-17 spend_tail #2: added≠rows → метрика недействительна (valid=False, rows_per_second=None).

    Красная сторона (проба C): стаб import_csv → added=0 давал отчёт «1000 строк,
    rows_per_second≈2.9e8» без пометки невалидности.
    """
    bench = _bench()
    import spendtrack.csv_import as ci

    real = ci.import_csv
    try:
        ci.import_csv = lambda *a, **k: {"added": 0}
        res = bench._import_case(rows=5, repeats=1)
    finally:
        ci.import_csv = real
    assert res["valid"] is False, res
    assert res["rows_per_second"] is None, res
    assert res["added"] == 0


def test_import_case_valid_control():
    """Положительный контроль: реальный (оффлайн) импорт 5 строк → valid, метрика есть."""
    bench = _bench()
    res = bench._import_case(rows=5, repeats=1)
    assert res["valid"] is True and res["added"] == 5 and res["rows_per_second"], res


def test_http_cases_flags_errors(tmp_path):
    """B-17 spend_tail #1: 503/редирект — ошибка на путь (не «median»); follow_redirects=False.

    Красная сторона (проба A/B): фейк-приложение отвечало 503 на оба пути → в отчёте обычные
    median (~4 мс); исключение давало {"error"} без упоминания HTTP и rc=0 у main.
    """
    bench = _bench()
    saved_env = os.environ.get("SPENDTRACK_DB_PATH")
    bad = _Client(503, "oops")
    out = bench._http_cases(tmp_path / "x.db", repeats=1, client=bad)
    assert set(out) == {"/", "/dashboard"}
    assert all("error" in out[p] for p in out), out
    assert os.environ.get("SPENDTRACK_DB_PATH") == saved_env, \
        "env SPENDTRACK_DB_PATH обязан восстанавливаться (слепая зона адъюдикации)"

    redir = _Client(307, "")
    out2 = bench._http_cases(tmp_path / "x.db", repeats=1, client=redir)
    assert all("error" in out2[p] for p in out2), out2

    good = _Client(200, '<div id="tx-table"></div><div id="kpi-balance"></div>')
    out3 = bench._http_cases(tmp_path / "x.db", repeats=1, client=good)
    assert all("median_ms" in out3[p] for p in out3), out3
    assert good.calls, "клиент обязан опрашиваться"
    assert all(kw.get("follow_redirects") is False for _p, kw in good.calls)


def test_incomplete_reasons_from_report():
    """#1/#2: сводка неполноты — http-ошибки и невалидный импорт попадают в reasons."""
    bench = _bench()
    bad = {"sizes": {"100": {"http": {"/": {"error": "HTTP 503"},
                                      "/dashboard": {"median_ms": 1.0}}}},
           "import": {"valid": False, "added": 0, "rows": 5}, "skip_http": False}
    reasons = bench._incomplete_reasons(bad)
    assert any("HTTP" in r for r in reasons), reasons
    assert any("import" in r for r in reasons), reasons

    good = {"sizes": {"100": {"http": {"/": {"median_ms": 1.0}}}},
            "import": {"valid": True}, "skip_http": False}
    assert bench._incomplete_reasons(good) == []

    skipped = {"sizes": {"100": {}}, "import": {"valid": True}, "skip_http": True}
    assert bench._incomplete_reasons(skipped) == [], "явный --skip-http — не неполнота"
