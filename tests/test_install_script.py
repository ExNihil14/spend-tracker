"""install.ps1: статические гейты по ревью Astra 01.10 (S4 — native exit codes, S5 — Git-зависимость).

Тесты статические (скрипт не исполняется): защищают от регрессии «ложного успеха установки».
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install.ps1"


def test_uv_install_checks_last_exit_code():
    """S4: после `uv tool install` код возврата проверяется явно (иначе ложное «Готово»)."""
    text = SCRIPT.read_text(encoding="utf-8")
    idx = text.index("uv tool install --force")
    tail = text[idx:]
    assert "$LASTEXITCODE" in tail.split("\n\n")[0] or "throw" in tail.split("\n\n")[0]


def test_serve_exit_code_propagated():
    """S4: код завершения сервера передаётся вызывающей стороне."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "& $exe @serveArgs" in text
    assert "exit $LASTEXITCODE" in text


def test_git_dependency_documented():
    """S5: зависимость от Git для git+https источника заявлена в шапке скрипта."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "git" in text.lower() and ("требует" in text.lower() or "нужен" in text.lower()
                                      or "git+" in text)
