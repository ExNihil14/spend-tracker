"""Гейты не должны выглядеть зелёными, когда измерять нечего (адъюдикация wave8, `gates`).

F2 (`ratchet.py`): `spec/ratchet_baseline.json` = `null` → `load_baseline()` возвращает `None`,
а `_cmd_check()` проверяет тип только при `baseline is not None`. В JSON-режиме гейт завершался
rc=0 с пустым `failures` (базлайн молча переставал участвовать в сравнении), в текстовом —
падал на `baseline.get(...)` вместо FAIL.

F3 (`cc_ratchet.py`): `run_ruff()` подменял ПУСТОЙ stdout на `[]`, поэтому сбой анализа ruff
(rc=1 без вывода) читался как «сложных функций нет»; диагностики не-C901 (например
`invalid-syntax` — битый синтаксис всё равно попадает в вывод при `--select C901`)
молча отбрасывались. Проверяем ПУБЛИЧНОЕ поведение: код возврата/исключение и текст.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REAL_RATCHET_BASELINE = ROOT / "spec" / "ratchet_baseline.json"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _ratchet_with_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str):
    """Модуль ratchet с подменённым путём базлайна и замером, возвращающим РЕАЛЬНЫЕ метрики.

    Замер подменяется, чтобы тест проверял ровно обработку базлайна (F2) и не тратил время на
    прогон SQL-счётчиков; значения берутся из настоящего базлайна, чтобы `compare()` не дала
    посторонних FAIL.
    """
    mod = _load("ratchet")
    path = tmp_path / "ratchet_baseline.json"
    path.write_text(text, encoding="utf-8")
    metrics = json.loads(REAL_RATCHET_BASELINE.read_text(encoding="utf-8"))["metrics"]
    monkeypatch.setattr(mod, "BASELINE_PATH", path)
    monkeypatch.setattr(mod, "measure", lambda: dict(metrics))
    return mod, metrics


def _capture_json_check(mod, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    rc = mod._cmd_check(True)
    payload = json.loads(capsys.readouterr().out)
    return rc, payload


# ─────────────────────────────────── F2: ratchet ───────────────────────────────────

def test_check_reports_null_baseline_in_json_mode(tmp_path, monkeypatch, capsys):
    """F2: `null` вместо базлайна → FAIL, а не тихий успех с пустым failures."""
    mod, _ = _ratchet_with_baseline(tmp_path, monkeypatch, "null")
    rc, payload = _capture_json_check(mod, capsys)

    assert rc == 1, f"ложный зелёный: rc={rc}, failures={payload['failures']}"
    assert payload["failures"], "базлайн=null не дал ни одной диагностики"


def test_check_survives_null_baseline_in_text_mode(tmp_path, monkeypatch, capsys):
    """F2: текстовый режим не должен падать AttributeError — гейт обязан печатать FAIL."""
    mod, _ = _ratchet_with_baseline(tmp_path, monkeypatch, "null")
    rc = mod._cmd_check(False)
    out = capsys.readouterr().out

    assert rc == 1, f"ожидался FAIL, rc={rc}"
    assert "FAIL" in out, out


def test_check_accepts_real_baseline(tmp_path, monkeypatch, capsys):
    """Контроль: настоящий базлайн остаётся зелёным (фикс не ломает рабочий путь)."""
    mod, _ = _ratchet_with_baseline(tmp_path, monkeypatch, REAL_RATCHET_BASELINE.read_text(encoding="utf-8"))
    rc, payload = _capture_json_check(mod, capsys)

    assert rc == 0, payload["failures"]
    assert payload["baseline"] is not None


# ─────────────────────────────────── F3: cc_ratchet ───────────────────────────────────

class _FakeProc:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_measure_rejects_ruff_failure_without_output(monkeypatch):
    """F3: ruff вернул rc=1 и пустой stdout → замер невозможен, а не «сложных функций нет»."""
    mod = _load("cc_ratchet")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc(1, "", "tool failed"))

    with pytest.raises(SystemExit):
        mod.run_ruff()


def test_measure_rejects_non_c901_diagnostics():
    """F3: `invalid-syntax` в выводе при `--select C901` → анализ неполон, замер невозможен."""
    mod = _load("cc_ratchet")
    payload = [{"code": "invalid-syntax", "message": "expected `}`", "filename": "x.py"}]

    with pytest.raises(SystemExit):
        mod.parse_or_fail(payload)


def test_measure_allows_clean_empty_result(monkeypatch):
    """Контроль: ruff отработал чисто (`[]`, rc=0) — «сложных функций нет» допустимо."""
    mod = _load("cc_ratchet")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc(0, "[]"))

    assert mod.run_ruff() == []


def test_measure_rejects_non_list_json(monkeypatch):
    """F3: ruff вернул не список диагностик (`{}`) — формат изменился, замер невозможен."""
    mod = _load("cc_ratchet")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc(0, "{}"))

    with pytest.raises(SystemExit):
        mod.run_ruff()
