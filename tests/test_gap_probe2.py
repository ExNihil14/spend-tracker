"""Регресс-оракулы гейтов (B-16, адъюдикация wave9 P3): should-пункты gatetests_opus/astra.

Закрепляют: композицию ruff→parse_or_fail (S2/#4), охрану КАЖДОГО базлайна независимым
литеральным путём (S4a), fail-closed на нечитаемые / не-объектные базлайны (S1), «текст трейлера
внутри диффа не авторизует» (S4b), членство имён ассетов в ASSETS (S3/#5).

Происхождение: валидированные в %TEMP%-копии оракулы из адъюдикации P3
(`ADJUDICATION_WAVE9_P3_2026-10-13.md` §2.1); перенесены в репозиторий без изменения проверок.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
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


class _FakeProc:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ── S2 (opus)/#4 (astra): вывод ruff обязан пройти parse_or_fail (маршрутизация в main) ──
def test_parse_or_fail_composes_with_run_ruff_on_non_c901(monkeypatch):
    """Раутинг делает main(); run_ruff() лишь разбирает JSON — композиция обязана падать."""
    mod = _load("cc_ratchet")
    bad = json.dumps([{"code": "invalid-syntax", "message": "x", "filename": "x.py"}])
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc(1, bad))
    with pytest.raises(SystemExit):
        mod.parse_or_fail(mod.run_ruff())


def test_main_check_rejects_non_c901_from_ruff(monkeypatch, tmp_path):
    """Сквозной путь main(): не-C901 диагностика обязана остановить гейт, а не раствориться."""
    mod = _load("cc_ratchet")
    baseline = tmp_path / "cc_baseline.json"
    baseline.write_text('{"schema": 1, "functions": {}}', encoding="utf-8")
    monkeypatch.setattr(mod, "BASELINE", baseline)
    bad = json.dumps([{"code": "invalid-syntax", "message": "x", "filename": "x.py"}])
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc(1, bad))
    with pytest.raises(SystemExit):
        mod.main(["check"])


def test_run_ruff_returns_findings_on_rc1(monkeypatch):
    mod = _load("cc_ratchet")
    ok = json.dumps([{"code": "C901", "filename": "a.py",
                      "message": "`f` is too complex (12 > 10)"}])
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc(1, ok))
    assert len(mod.run_ruff()) == 1


# ── S4a (opus): КАЖДЫЙ охраняемый базлайн обязан быть закрыт (литеральный пин, не из модуля) ──
def _repo_with(tmp_path, rel: str, change_to: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / Path(rel).parent).mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text('{"schema": 1}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    (repo / rel).write_text(change_to, encoding="utf-8")
    git("commit", "-qam", "change without trailer")
    return repo


def test_ratchet_baseline_change_is_guarded(tmp_path):
    mod = _load("baseline_guard")
    repo = _repo_with(tmp_path, "spec/ratchet_baseline.json", '{"schema": 2}')
    old = mod.ROOT
    mod.ROOT = repo
    try:
        rc = mod.main(["--base", "HEAD~1", "--head", "HEAD"])
    finally:
        mod.ROOT = old
    assert rc == 1, "изменение spec/ratchet_baseline.json без трейлера обязано падать"


def test_cc_baseline_change_is_guarded(tmp_path):
    mod = _load("baseline_guard")
    repo = _repo_with(tmp_path, "spec/cc_baseline.json", '{"schema": 2}')
    old = mod.ROOT
    mod.ROOT = repo
    try:
        rc = mod.main(["--base", "HEAD~1", "--head", "HEAD"])
    finally:
        mod.ROOT = old
    assert rc == 1, "изменение spec/cc_baseline.json без трейлера обязано падать"


# ── S1 (opus): нечитаемые базлайны обязаны падать fail-closed в обоих режимах ──
def _ratchet_with(tmp_path, monkeypatch, text: str | None):
    mod = _load("ratchet")
    if text is None:
        path = tmp_path / "missing.json"
    else:
        path = tmp_path / "ratchet_baseline.json"
        path.write_text(text, encoding="utf-8")
    metrics = json.loads(REAL_RATCHET_BASELINE.read_text(encoding="utf-8"))["metrics"]
    monkeypatch.setattr(mod, "BASELINE_PATH", path)
    monkeypatch.setattr(mod, "measure", lambda: dict(metrics))
    return mod


@pytest.mark.parametrize("text", ["null", "{}", "[]", '"x"', '{"metrics": null}', "{not json", None])
def test_unusable_baseline_fails_closed_json(tmp_path, monkeypatch, capsys, text):
    mod = _ratchet_with(tmp_path, monkeypatch, text)
    rc = mod._cmd_check(True)
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1 and payload["failures"], f"{text!r}: rc={rc}, failures={payload['failures']}"


@pytest.mark.parametrize("text", ["null", "{}", "[]", '"x"', '{"metrics": null}', "{not json", None])
def test_unusable_baseline_fails_closed_text(tmp_path, monkeypatch, capsys, text):
    mod = _ratchet_with(tmp_path, monkeypatch, text)
    rc = mod._cmd_check(False)
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL" in out, f"{text!r}: rc={rc}"


# ── S4b (opus): текст трейлера внутри диффа НЕ авторизует ──
def test_trailer_text_inside_diff_does_not_authorize(tmp_path):
    mod = _load("baseline_guard")
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / "spec").mkdir()
    (repo / "spec" / "contract_baseline.json").write_text('{"schema": 1}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    (repo / "spec" / "contract_baseline.json").write_text(
        '{"note": "Contract-Change: schema=2"}', encoding="utf-8")
    git("commit", "-qam", "sneak")
    old_root = mod.ROOT
    mod.ROOT = repo
    try:
        rc = mod.main(["--base", "HEAD~1", "--head", "HEAD"])
    finally:
        mod.ROOT = old_root
    assert rc == 1, "текст трейлера внутри диффа не должен авторизовать изменение базлайна"


# ── S3 (opus)/astra #5: имена ассетов обязаны иметь digest в ASSETS ──
def test_asset_names_membership_against_assets():
    bc = _load("build_css")
    for _system, _machine, expected in [
        ("darwin", "x86_64", "tailwindcss-macos-x64"),
        ("darwin", "arm64", "tailwindcss-macos-arm64"),
        ("linux", "x86_64", "tailwindcss-linux-x64"),
        ("win32", "AMD64", "tailwindcss-windows-x64.exe"),
    ]:
        assert expected in bc.ASSETS, f"нет digest для {expected}"
