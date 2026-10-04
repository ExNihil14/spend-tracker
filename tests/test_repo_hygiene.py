"""Стат-гарды репо-гигиены (Habr-ресёрч 04.10): защита секретов не должна исчезнуть из репо."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pre_commit_gitleaks_pinned():
    cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "gitleaks-system" in cfg and "rev: v8." in cfg  # пин версии + system-hook (без Go/Docker)
    # без этого pre-commit передаёт имя файла аргументом → gitleaks трактует его как [repo] и молча пропускает
    assert "pass_filenames: false" in cfg


def test_ci_secret_scan_job_present():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "secret-scan" in ci and "gitleaks" in ci
