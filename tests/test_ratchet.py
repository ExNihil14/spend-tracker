"""Ratchet-метрики: форма baseline, детект регресса, CLI check. Оффлайн, прод не трогает."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

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
