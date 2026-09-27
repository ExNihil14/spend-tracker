"""Регресс визуальных ассетов README и плана их пересъёмки — оффлайн, без сети и браузера.

Ловит: ссылку README на несуществующую картинку (переименование/потеря файла) и расхождение
`scripts/record_readme_screens.py` с фактическими ссылками на `assets/screenshot-*.png`
(пересъёмка — вручную: `uv run python scripts/record_readme_screens.py`).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SCRIPT = ROOT / "scripts" / "record_readme_screens.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("record_readme_screens", SCRIPT)
    assert spec and spec.loader, "scripts/record_readme_screens.py не найден"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_readme_local_images_exist():
    refs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", README.read_text(encoding="utf-8"))
    local = [r for r in refs if not r.startswith(("http://", "https://"))]
    assert local, "README: нет локальных картинок"
    missing = [r for r in local if not (ROOT / r.split("?")[0]).is_file()]
    assert missing == [], f"README ссылается на отсутствующие файлы: {missing}"


def test_capture_plan_covers_readme_screenshots():
    plan = {name for name, _, _ in _load_script().PLAN}
    refs = set(re.findall(r"assets/(screenshot-[\w.-]+\.png)", README.read_text(encoding="utf-8")))
    assert refs == plan, f"план съёмки и README разошлись: {refs ^ plan}"
