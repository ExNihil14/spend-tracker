from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "review_script", ROOT / "scripts" / "review.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_load_checklist_falls_back_to_embedded(tmp_path):
    text = _mod().load_checklist(tmp_path / "missing.md")

    assert "Контракт-дельта" in text
    assert "10." in text


def test_render_prompt_contains_checklist_plan_and_artifacts():
    m = _mod()
    prompt = m.render_prompt(
        title="Тестовая задача",
        checklist="1. Проверить границы",
        notes="проверено фактом: 275 unit зелёные",
        diff_stat=" a.py | 2 +-",
        diff="diff --git a/a.py b/a.py\n+new line",
        extras={"new_module.py": "def f() -> int:\n    return 1\n"},
    )

    assert "# Что ревьюится: Тестовая задача" in prompt
    assert "1. Проверить границы" in prompt
    assert "P0/P1 **планом пунктами**" in prompt
    assert "проверено фактом: 275 unit зелёные" in prompt
    assert "+new line" in prompt
    assert "new_module.py" in prompt
