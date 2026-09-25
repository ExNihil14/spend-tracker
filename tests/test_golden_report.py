"""Golden-набор мерчантов (§G-4): консистентность набора и метрики отчётного скрипта."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from spendtrack.categorize import categorize_rules_only
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "golden_report.py"
GOLDEN = ROOT / "tests" / "golden" / "merchants.csv"


def _mod():
    spec = importlib.util.spec_from_file_location("golden_report", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_compute_metrics_on_tiny_stub():
    """Метрики считаются по контракту: хиты/ошибки/нерешённые/сюрпризы."""
    rows = [
        {"description": "A", "expected": "groceries", "bank": ""},
        {"description": "B", "expected": "fuel", "bank": ""},
        {"description": "C", "expected": "fuel", "bank": ""},
        {"description": "D", "expected": "", "bank": ""},
    ]
    got = {"A": "groceries", "B": "other", "C": None, "D": "groceries"}
    report = _mod().compute(rows, lambda r: got[r["description"]])
    assert report["known"] == 3 and report["known_hit"] == 1
    assert report["misclassified"] == 1   # B: «other» вместо fuel
    assert report["unresolved"] == 1      # C: правила не нашли
    assert report["surprise"] == 1        # D: правило сработало без ожидания
    assert report["rule_hit_share"] == round(1 / 3, 4)
    assert report["details"]["missed"]


def test_golden_set_well_formed_and_rules_consistent(tmp_path):
    """Набор ≥30 строк, ожидания — слаги таксономии; на текущем наборе правила без ошибок,
    а неизвестные строки действительно остаются нерешёнными (иначе метрика неинформативна)."""
    mod = _mod()
    rows = mod.load_rows(GOLDEN)
    assert len(rows) >= 30

    taxonomy = load_taxonomy()
    valid = {c.name for c in taxonomy.categories}
    assert all(r["expected"] in valid for r in rows if r["expected"])

    store = Store(db_path=tmp_path / "golden.db")
    try:
        def classify(row: dict) -> str | None:
            return categorize_rules_only(
                {"description": row["description"], "merchant": row["description"]}, taxonomy, store)

        report = mod.compute(rows, classify)
    finally:
        store.close()

    assert report["misclassified"] == 0, report["details"]["missed"]
    assert report["surprise"] == 0, report["details"]["surprise"]
    assert report["rule_hit_share"] >= 0.9, report["details"]["missed"]
    assert report["unresolved"] >= 5  # есть строки для LLM/очереди — набор не «самоподтверждающийся»
