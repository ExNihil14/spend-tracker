"""Стат-гарды репо-гигиены (Habr-ресёрч 04.10): защита секретов не должна исчезнуть из репо.

Структурные проверки (Astra site_tail, 05.10): разбираем YAML и проверяем АКТИВНЫЕ узлы —
закомментированная конфигурация больше не проходит (раньше подстрочный поиск её пропускал).
pyyaml приходит с `uvicorn[standard]` (прямая зависимость) — новых зависимостей нет.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _gitleaks_repo(cfg: dict) -> dict | None:
    """Активный (не закомментированный) repo-блок gitleaks в .pre-commit-config.yaml."""
    for repo in (cfg or {}).get("repos") or []:
        if str(repo.get("repo", "")).rstrip("/").endswith("gitleaks/gitleaks"):
            return repo
    return None


def test_pre_commit_gitleaks_pinned():
    cfg = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    repo = _gitleaks_repo(cfg)
    assert repo is not None, "активный repo gitleaks/gitleaks не найден (закомментирован?)"
    assert str(repo.get("rev", "")).startswith("v8."), f"пин версии потерян: {repo.get('rev')!r}"
    hooks = [h for h in repo.get("hooks") or [] if h.get("id") == "gitleaks-system"]
    assert hooks, "активный hook gitleaks-system не найден"
    # без этого pre-commit передаёт имя файла аргументом → gitleaks трактует его как [repo] и молча пропускает
    assert hooks[0].get("pass_filenames") is False


def test_repo_hygiene_guard_rejects_commented_config():
    """Само-проверка гарда: закомментированные строки для YAML не существуют (раньше «проходили»)."""
    commented = (
        "repos:\n"
        "  # - repo: https://github.com/gitleaks/gitleaks\n"
        "  #   rev: v8.30.1\n"
        "  #   hooks:\n"
        "  #     - id: gitleaks-system\n"
        "  #       pass_filenames: false\n"
    )
    assert _gitleaks_repo(yaml.safe_load(commented)) is None


def test_ci_secret_scan_job_present():
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = (ci.get("jobs") or {}).get("secret-scan")
    assert job is not None, "job secret-scan отсутствует/закомментирован"
    uses = " ".join(str(s.get("uses", "")) for s in job.get("steps") or [])
    assert "gitleaks" in uses, "шаг с gitleaks-action не найден в secret-scan"
