"""CI-гейт: изменение базлайнов допустимо только с трейлером `Contract-Change: <причина>`.

Проверяет диапазон коммитов `--base .. --head`: если в нём изменён `spec/contract_baseline.json`
или `spec/ratchet_baseline.json`, то хотя бы один коммит диапазона обязан содержать трейлер
`Contract-Change: <причина>` в теле. Закрывает обход «дрейф контракта + snapshot в одном коммите»
(ревью Opus 5.5, C5): локальная команда snapshot больше не «самоутверждает» гейт.

Использование:
    uv run python scripts/baseline_guard.py --base origin/main [--head HEAD]
    # CI: PR → origin/<base_ref>; push → ${{ github.event.before }}
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ("spec/contract_baseline.json", "spec/ratchet_baseline.json")
TRAILER = re.compile(r"^Contract-Change:\s*\S+", re.MULTILINE)


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    return result.stdout or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Гейт трейлера Contract-Change для базлайнов")
    parser.add_argument("--base", required=True, help="базовая ссылка/хеш (origin/main, event.before)")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)

    base = args.base.strip()
    if not base or set(base) <= {"0"}:  # push с нулевым before (первый push ветки) — диапазона нет
        print("baseline guard: base пустой/нулевой — пропуск (нет диапазона)")
        return 0
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", base], cwd=ROOT,
                      capture_output=True, check=False).returncode != 0:
        print(f"baseline guard: base {base!r} не найден — пропуск (не блокируем)")
        return 0

    changed = _git("diff", "--name-only", f"{base}..{args.head}").splitlines()
    touched = [b for b in BASELINES if b in changed]
    if not touched:
        print("baseline guard: базлайны не менялись — ok")
        return 0
    log = _git("log", f"{base}..{args.head}", "--format=%B")
    if TRAILER.search(log):
        print(f"baseline guard: изменены {touched}; трейлер Contract-Change найден — ok")
        return 0
    print(f"baseline guard: FAIL — изменены {touched} без трейлера "
          "`Contract-Change: <причина>` в коммитах диапазона")
    return 1


if __name__ == "__main__":
    sys.exit(main())
