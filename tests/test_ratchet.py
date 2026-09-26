"""Ratchet-метрики: форма baseline, детект регресса и ложных гарантий, CLI check. Оффлайн, прод не трогает."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ratchet.py"
BASELINE = ROOT / "spec" / "ratchet_baseline.json"


def _module():
    spec = importlib.util.spec_from_file_location("ratchet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_baseline_shape():
    metrics = json.loads(BASELINE.read_text(encoding="utf-8"))["metrics"]
    assert metrics["report_month_queries"] > 0
    assert metrics["import_100_queries"] > 0
    assert metrics["categorize_100_ms"] > 0


def test_compare_detects_regression():
    mod = _module()
    baseline = {"metrics": {"report_month_queries": 2, "import_100_queries": 435}}
    assert mod.compare(baseline, {"report_month_queries": 2, "import_100_queries": 435}) == []
    failures = mod.compare(baseline, {"report_month_queries": 3, "import_100_queries": 435})
    assert failures and "report_month_queries" in failures[0]


def test_compare_missing_metric_is_failure():
    """Метрики нет в базлайне или замере — это FAIL, а не молчаливое «гейта нет»."""
    mod = _module()
    good = {"report_month_queries": 2, "import_100_queries": 435}
    in_baseline = mod.compare({"metrics": {"report_month_queries": 2}}, good)
    assert len(in_baseline) == 1 and "import_100_queries" in in_baseline[0] and "базлайне" in in_baseline[0]
    in_current = mod.compare({"metrics": good}, {"report_month_queries": 2})
    assert len(in_current) == 1 and "import_100_queries" in in_current[0] and "замере" in in_current[0]


def test_compare_suspiciously_low_is_failure():
    """«Слишком хорошо» (0 или < 0.5×базлайна) — поломка замера, а не оптимизация."""
    mod = _module()
    baseline = {"metrics": {"report_month_queries": 2, "import_100_queries": 400}}
    assert mod.compare(baseline, {"report_month_queries": 1, "import_100_queries": 399}) == []
    half = mod.compare(baseline, {"report_month_queries": 1, "import_100_queries": 200})
    assert half == []  # граница: ровно 0.5× — ещё не «слишком хорошо»
    low = mod.compare(baseline, {"report_month_queries": 1, "import_100_queries": 199})
    assert low and "import_100_queries" in low[0] and "слишком хорошо" in low[0]
    zero = mod.compare(baseline, {"report_month_queries": 0, "import_100_queries": 435})
    assert zero and "report_month_queries" in zero[0]


def test_compare_non_numeric_is_failure_not_crash():
    """None/строка в метрике — FAIL в обоих режимах (раньше текстовый режим падал TypeError)."""
    mod = _module()
    baseline = {"metrics": {"report_month_queries": None, "import_100_queries": 435}}
    failures = mod.compare(baseline, {"report_month_queries": 2, "import_100_queries": "x"})
    assert len(failures) == 2
    assert "report_month_queries" in failures[0] and "import_100_queries" in failures[1]


def test_measure_rejects_dead_import(monkeypatch):
    """Сломанный генератор выписки («0 добавлено») — замер отбрасывается, а не «улучшается»."""
    mod = _module()
    monkeypatch.setattr(mod, "_gen_sber_email", lambda n=100, seed=7: "мусор;мусор\n")
    with pytest.raises(AssertionError):
        mod.measure()


def test_measure_rejects_empty_seed(monkeypatch):
    """Пустой seed — метрики SQL недостоверны, замер отбрасывается."""
    mod = _module()
    monkeypatch.setattr(mod, "_seed", lambda store: None)
    with pytest.raises(AssertionError):
        mod.measure()


def test_cli_check_fails_on_baseline_without_metrics(tmp_path, monkeypatch, capsys):
    """Порча базлайна = FAIL и без, и с --json (раньше: exit 0 в --json, TypeError в тексте)."""
    mod = _module()
    monkeypatch.setattr(mod, "measure",
                        lambda: {"report_month_queries": 2, "import_100_queries": 435})
    broken = tmp_path / "ratchet_baseline.json"
    broken.write_text(json.dumps({"version": 1, "metrics": {}}), encoding="utf-8")
    monkeypatch.setattr(mod, "BASELINE_PATH", broken)

    assert mod._cmd_check(False) == 1
    text_out = capsys.readouterr().out
    assert text_out.count("FAIL") == 2 and "—" in text_out

    assert mod._cmd_check(True) == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["failures"]) == 2
    assert all("базлайне" in f for f in payload["failures"])


def test_cli_check_fails_without_baseline_file(tmp_path, monkeypatch, capsys):
    mod = _module()
    monkeypatch.setattr(mod, "measure",
                        lambda: {"report_month_queries": 2, "import_100_queries": 435})
    monkeypatch.setattr(mod, "BASELINE_PATH", tmp_path / "nope.json")
    assert mod._cmd_check(True) == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["failures"]) == 1 and "базлайн" in payload["failures"][0]


def test_cli_check_fails_on_unknown_baseline_version(tmp_path, monkeypatch, capsys):
    mod = _module()
    monkeypatch.setattr(mod, "measure",
                        lambda: {"report_month_queries": 2, "import_100_queries": 435})
    drifted = tmp_path / "ratchet_baseline.json"
    drifted.write_text(json.dumps({"version": 2, "metrics": {}}), encoding="utf-8")
    monkeypatch.setattr(mod, "BASELINE_PATH", drifted)
    assert mod._cmd_check(True) == 1
    failures = json.loads(capsys.readouterr().out)["failures"]
    assert any("версия" in f for f in failures)


def test_cli_check_green():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
