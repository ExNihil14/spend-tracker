"""Тесты GIF-генератора лендинга (§G-7): guard demo-БД и сборка GIF (без браузера/сети)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "record_demo_gif.py"


def _mod():
    spec = importlib.util.spec_from_file_location("record_demo_gif", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_is_demo_db_guard():
    mod = _mod()
    assert mod.is_demo_db(Path("data/demo.db"))
    assert not mod.is_demo_db(Path("data/spend.db"))
    assert not mod.is_demo_db(Path("demo.db.bak"))


def test_assemble_gif_resizes_and_loops(tmp_path):
    """Кадры разного размера → единая ширина, 2 кадра, подписи не ломают сборку."""
    mod = _mod()
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    Image.new("RGB", (400, 300), (200, 30, 30)).save(first)
    Image.new("RGB", (800, 600), (30, 30, 200)).save(second)

    out = mod.assemble_gif([first, second], tmp_path / "demo.gif",
                           width=320, seconds=0.2, captions=("Первый", "Второй"))
    assert out.is_file() and out.stat().st_size > 0
    with Image.open(out) as gif:
        assert gif.n_frames == 2
        assert gif.size[0] == 320


def test_assemble_gif_rejects_empty(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        _mod().assemble_gif([], tmp_path / "empty.gif")
