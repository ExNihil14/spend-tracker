"""CI-гейт: изменение базлайнов допустимо только с трейлером `Contract-Change: <причина>`.

Проверяет диапазон коммитов `--base .. --head`: если в нём изменён `spec/contract_baseline.json`,
`spec/ratchet_baseline.json` или `spec/cc_baseline.json`, то хотя бы один коммит диапазона обязан содержать
трейлер `Contract-Change: <причина>` в теле. Закрывает обход «дрейф контракта + snapshot в одном коммите»
(ревью Opus 5.5, C5): локальная команда snapshot больше не «самоутверждает» гейт.

F1 (адъюдикация wave8, `gates`): невозможность ПРОВЕРИТЬ больше не выглядит как успех.
Раньше несуществующая ссылка (shallow checkout, не fetched `origin/main`, опечатка в CI) и любая
ошибка git давали rc=0 с тем же текстом «базлайны не менялись — ok», что и исправный забег, —
изменение baseline проходило молча. Теперь: обе ссылки проверяются как КОММИТЫ, любой ненулевой
код git — это rc=2 (ошибка гейта, не нарушение политики). Для первого push ветки (`before` = нули)
диапазона нет: сравниваем с `origin/main`, если он доступен; иначе — явная пропуск с пометкой.

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
BASELINES = ("spec/contract_baseline.json", "spec/ratchet_baseline.json", "spec/cc_baseline.json")
# Трейлер и причина — в ОДНОЙ строке: `\s*` раньше позволял перескочить перевод строки и «проверить»
# трейлер с пустой причиной (F7). Причина обязана быть непустой.
TRAILER = re.compile(r"^Contract-Change:[ \t]+(\S.*)$", re.MULTILINE)


def _git(*args: str) -> tuple[int, str]:
    """Возвращает (код, stdout). Код проверяет вызывающий — ошибка git не значит «изменений нет»."""
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    return result.returncode, result.stdout or ""


def _is_commit(ref: str) -> bool:
    """Ссылка разрешается именно в коммит (не в тег/дерево/мусор)."""
    rc, _ = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return rc == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Гейт трейлера Contract-Change для базлайнов")
    parser.add_argument("--base", required=True, help="базовая ссылка/хеш (origin/main, event.before)")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)

    base = args.base.strip()
    head = args.head.strip()
    if not base or set(base) <= {"0"}:
        # Первый push ветки: диапазона «до» не существует. Сравниваем с основной веткой, если она есть.
        if _is_commit("origin/main"):
            print("baseline guard: base пустой/нулевой (первый push ветки) — сравниваю с origin/main")
            base = "origin/main"
        else:
            print("baseline guard: base пустой/нулевой и origin/main недоступен — диапазона нет, пропуск")
            return 0
    for ref in (base, head):
        if not _is_commit(ref):
            print(f"baseline guard: ссылка {ref!r} не разрешается в коммит — проверка невозможна "
                  "(shallow clone? не выполнен fetch? опечатка?) — FAIL")
            return 2

    rc, changed_out = _git("diff", "--name-only", f"{base}..{head}")
    if rc != 0:
        print(f"baseline guard: `git diff {base}..{head}` завершился с кодом {rc} — проверка невозможна — FAIL")
        return 2
    changed = changed_out.splitlines()
    touched = [b for b in BASELINES if b in changed]
    if not touched:
        print("baseline guard: базлайны не менялись — ok")
        return 0
    rc, log = _git("log", f"{base}..{head}", "--format=%B")
    if rc != 0:
        print(f"baseline guard: `git log {base}..{head}` завершился с кодом {rc} — проверка невозможна — FAIL")
        return 2
    if TRAILER.search(log):
        print(f"baseline guard: изменены {touched}; трейлер Contract-Change найден — ok")
        return 0
    print(f"baseline guard: FAIL — изменены {touched} без трейлера "
          "`Contract-Change: <причина>` в коммитах диапазона")
    return 1


if __name__ == "__main__":
    sys.exit(main())
