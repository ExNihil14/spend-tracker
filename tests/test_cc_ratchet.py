"""Тесты cc_ratchet: парсинг C901, сравнение с baseline, запрет повышения без --force."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("cc_ratchet", ROOT / "scripts" / "cc_ratchet.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_parse_c901_extracts_functions_only():
    payload = [
        {"code": "C901", "message": "`build` is too complex (21 > 10)",
         "filename": str(ROOT / "scripts" / "demo_data.py")},
        {"code": "F401", "message": "unused import", "filename": str(ROOT / "src" / "x.py")},
    ]
    assert _mod().parse_c901(payload) == {"scripts/demo_data.py::build": 21}


def test_compare_flags_growth_and_new_function():
    fails, notes = _mod().compare(
        {"a.py::f": 12, "b.py::g": 11}, {"a.py::f": 11, "c.py::h": 12})

    assert any("выросла" in f for f in fails), fails
    assert any("новая функция" in f for f in fails), fails
    assert any("неактуальна" in n for n in notes), notes


def test_compare_notes_decrease_only():
    fails, notes = _mod().compare({"a.py::f": 9}, {"a.py::f": 11})

    assert fails == []
    assert notes and "снизилась" in notes[0]


def test_raised_detects_only_increases():
    m = _mod()

    assert m.raised({"a.py::f": 12}, {"a.py::f": 11}) == {"a.py::f": (11, 12)}
    assert m.raised({"a.py::f": 10}, {"a.py::f": 11}) == {}
    assert m.raised({"new.py::g": 12}, {}) == {"new.py::g": (None, 12)}


def test_baseline_file_shape():
    data = json.loads((ROOT / "spec" / "cc_baseline.json").read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["functions"]
    assert all(isinstance(v, int) and v > 10 for v in data["functions"].values())


def test_parse_or_fail_rejects_unknown_message_format():
    """Fail-closed: C901 есть, но формат сообщения не разобран → это дрейф, а не «всё хорошо»."""
    import pytest

    payload = [{"code": "C901", "message": "complexity 42 (новый формат ruff)",
                "filename": str(ROOT / "x.py")}]
    with pytest.raises(SystemExit):
        _mod().parse_or_fail(payload)


def test_live_ruff_parsing_matches_baseline():
    """Живой прогон: парсер и baseline согласованы с текущей версией ruff (ловит дрейф формата в CI)."""
    m = _mod()
    current = m.parse_or_fail(m.run_ruff())
    baseline = json.loads((ROOT / "spec" / "cc_baseline.json").read_text(encoding="utf-8"))["functions"]

    assert set(current) == set(baseline), f"парсер/baseline разошлись: {set(current) ^ set(baseline)}"
