"""F1 (адъюдикация wave8, `gates`): baseline_guard не должен отвечать «ok», когда проверить нельзя.

Дефект: несуществующая ссылка (shallow checkout, не fetched `origin/main`, опечатка в CI) и
любая ошибка git давали rc=0 с тем же текстом «базлайны не менялись — ok», что и успешный
забег. Сломанный гейт при этом неотличим от исправного, а изменение baseline проходит молча.

Проверяем ПУБЛИЧНОЕ поведение: код возврата `main()` и текст сообщения. Репозиторий —
настоящий временный git (mock stdout не способен поймать именно этот класс отказов).
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("baseline_guard", ROOT / "scripts" / "baseline_guard.py")
bg = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bg)

BASELINE = "spec/contract_baseline.json"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Временный репозиторий с одним коммитом; сам скрипт переводим на него (ROOT + cwd)."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "spec").mkdir()
    (tmp_path / BASELINE).write_text('{"schema": 1}', encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.setattr(bg, "ROOT", tmp_path)
    return tmp_path


def test_valid_range_without_baseline_change_is_ok(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Контроль зелёного: диапазон есть, baseline не тронут → rc=0."""
    assert bg.main(["--base", "HEAD", "--head", "HEAD"]) == 0
    assert "ok" in capsys.readouterr().out


def test_baseline_change_without_trailer_fails(repo: Path) -> None:
    """Контроль красного: baseline изменён без трейлера → rc=1."""
    (repo / BASELINE).write_text('{"schema": 2}', encoding="utf-8")
    _git(repo, "commit", "-qam", "bump schema")
    assert bg.main(["--base", "HEAD~1", "--head", "HEAD"]) == 1


def test_baseline_change_with_trailer_passes(repo: Path) -> None:
    """Контроль: baseline изменён С трейлером → rc=0."""
    (repo / BASELINE).write_text('{"schema": 2}', encoding="utf-8")
    _git(repo, "commit", "-qam", "bump schema\n\nContract-Change: schema=2")
    assert bg.main(["--base", "HEAD~1", "--head", "HEAD"]) == 0


def test_unknown_base_ref_is_not_success(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """F1: ссылки нет (shallow/не fetched/опечатка) → НЕ «ok»."""
    rc = bg.main(["--base", "origin/не-такой-ветки"])
    out = capsys.readouterr().out
    assert rc != 0, f"fail-open: неизвестная ссылка дала rc=0 ({out!r})"


def test_unknown_head_ref_is_not_success(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """F1: `git diff base..head` падает — гейт обязан сообщить об ошибке, а не «базлайны не менялись»."""
    rc = bg.main(["--base", "HEAD", "--head", "DOES_NOT_EXIST"])
    out = capsys.readouterr().out
    assert rc != 0, f"fail-open: несуществующий head дал rc=0 ({out!r})"
    assert "базлайны не менялись" not in out, f"ошибка git выдана за успех: {out!r}"


def test_broken_run_is_distinguishable_from_ok_run(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """F1: битый head и корректный диапазон не должны выглядеть одинаково."""
    bg.main(["--base", "HEAD", "--head", "DOES_NOT_EXIST"])
    broken = capsys.readouterr().out
    rc_ok = bg.main(["--base", "HEAD", "--head", "HEAD"])
    good = capsys.readouterr().out
    assert rc_ok == 0
    assert broken != good, "текст при ошибке git совпал с текстом успеха"
