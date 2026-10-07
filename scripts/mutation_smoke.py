"""Мутационная проба денежного ядра: измеряет СИЛУ ОРАКУЛОВ машинно, а не мнением.

Зачем. В бэклоге есть класс «сила оракулов в тестах» (BACKLOG §3: `tests_ui` 1–14, `tests_money`
S2–S5/S7–S10, `ops_b` #2–#7, `ui` 2–5) — находки вида «тест не доказывает заявленное». Ответ на
этот класс даёт мутационная проба: если мутация в коде не замечена тестами, значит оракул дырявый.
Это независимое, самодостаточное ревью: не нужен ни внешний канал, ни сеть.

Как. Правки текста по строкам (без зависимостей вроде mutmut/cosmic-ray), прогон целевого
подмножества тестов на каждом мутанте, атомарный откат.

Безопасность (важно — файл ядра):
  * скрипт отказывается работать, если `git status` по целевому файлу не чист (иначе откат затрёт
    чужую правку);
  * оригинал сохраняется в памяти, восстанавливается в `finally`, в конце сверяется sha256;
  * ни одна мутация не остаётся в дереве: при расхождении хэша скрипт падает с rc=2.

Ограничение (честно): прогоняется ЦЕЛЕВОЕ подмножество тестов, поэтому переживший мутант — это
гипотеза «оракул дырявый», которую надо подтвердить (например, прогнать более широкий набор).
Первый настоящий результат: `limit_value` пережил подмножество и подтвердился чтением тестов —
они сравнивают с самой константой, а не с её значением; значение закреплено отдельным тестом.

Запуск:  uv run python scripts/mutation_smoke.py [--only NAME] [--list]
Exit: 0 — проба выполнена (пережившие мутанты = находки, печатаются); 2 — сбой безопасности.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "spendtrack" / "store.py"
TESTS = ["tests/test_amounts.py", "tests/test_store_helpers.py", "tests/test_goals.py"]

# (имя, что меняем, на что, сколько вхождений ожидаем)
MUTANTS: list[tuple[str, str, str, int]] = [
    ("parse_int_scale", "        return value * 100\n", "        return value * 1000\n", 1),
    ("quantize_step", 'Decimal("0.01")', 'Decimal("0.1")', 1),
    ("rounding_mode", "rounding=ROUND_HALF_UP", "rounding=ROUND_HALF_EVEN", 1),
    ("limit_value", "MAX_AMOUNT_KOPECKS = 100_000_000_000",
     "MAX_AMOUNT_KOPECKS = 10_000_000_000", 1),
    ("fmt_sign", 'sign = "-" if kopecks < 0 else ""', 'sign = "-" if kopecks <= 0 else ""', 1),
    ("fmt_scale", 'abs(kopecks) / 100:.2f', 'abs(kopecks) / 1000:.2f', 2),
    ("signed_zero", '    if kopecks == 0:\n        return "0.00"',
     '    if kopecks >= 0:\n        return "0.00"', 1),
    ("signed_sign", 'sign = "\\u2212" if kopecks < 0 else "+"', 'sign = "+"', 1),
    ("nan_guard", "if not d.is_finite():", "if False:", 1),
    ("amount_upper_bound", "0 < abs(amount_kopecks) <= MAX_AMOUNT_KOPECKS",
     "0 < abs(amount_kopecks) < MAX_AMOUNT_KOPECKS", 1),
]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_clean(path: Path) -> tuple[bool, str]:
    rel = path.relative_to(ROOT).as_posix()
    out = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", rel],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         check=False)
    dirty = bool(out.stdout.strip())
    return (not dirty), out.stdout.strip()


def tests_pass() -> bool:
    """True — тесты ПРОШЛИ (мутант выжил). False — упали (мутант убит)."""
    out = subprocess.run(["uv", "run", "pytest", *TESTS, "-q", "-x", "--no-header",
                          "-p", "no:cacheprovider"],
                         cwd=str(ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    return out.returncode == 0


def run_probe(selected: list[tuple[str, str, str, int]], original: str,
              original_hash: str) -> tuple[list[str], list[str], list[tuple[str, str]], bool]:
    """Прогоняет мутантов. Возвращает (убитые, пережившие, пропущенные, файл_цел)."""
    killed: list[str] = []
    survived: list[str] = []
    skipped: list[tuple[str, str]] = []
    intact = True
    for name, old, new, expect in selected:
        cnt = original.count(old)
        if cnt != expect:
            skipped.append((name, f"образец встречается {cnt} раз, ожидалось {expect}"))
            continue
        mutated = original.replace(old, new, 1) if expect == 1 else original.replace(old, new)
        TARGET.write_text(mutated, encoding="utf-8")
        try:
            alive = tests_pass()
        finally:
            TARGET.write_text(original, encoding="utf-8")
        if sha(TARGET.read_text(encoding="utf-8")) != original_hash:
            intact = False
            break
        (survived if alive else killed).append(name)
        print(f"  {'ПЕРЕЖИЛ ' if alive else 'убит   '} {name}")
    return killed, survived, skipped, intact


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Мутационная проба денежного ядра")
    ap.add_argument("--only", default="", help="прогнать только мутант с этим именем")
    ap.add_argument("--list", action="store_true", help="показать список мутантов и выйти")
    args = ap.parse_args(argv[1:])

    if args.list:
        for name, old, new, _cnt in MUTANTS:
            print(f"  {name:<20} {old.strip()[:40]!r} -> {new.strip()[:40]!r}")
        return 0

    clean, dirty = git_clean(TARGET)
    if not clean:
        print(f"ОТКАЗ: целевой файл изменён в дереве ({dirty}) — откат затрёт правку", file=sys.stderr)
        return 2

    original = TARGET.read_text(encoding="utf-8")
    original_hash = sha(original)
    selected = [m for m in MUTANTS if not args.only or m[0] == args.only]
    if not selected:
        print(f"нет мутанта с именем {args.only!r}", file=sys.stderr)
        return 2

    print(f"цель: {TARGET.relative_to(ROOT)} ({len(original.splitlines())} строк), "
          f"тесты: {', '.join(TESTS)}")
    print(f"мутантов: {len(selected)}\n")

    try:
        killed, survived, skipped, intact = run_probe(selected, original, original_hash)
    finally:
        TARGET.write_text(original, encoding="utf-8")

    restored = sha(TARGET.read_text(encoding="utf-8")) == original_hash
    print(f"\nвосстановление файла: {'OK (sha256 совпал)' if restored else 'СБОЙ'}")
    if not (intact and restored):
        return 2

    total = len(killed) + len(survived)
    score = (len(killed) / total * 100) if total else 0.0
    print(f"\nИТОГ: убито {len(killed)} / {total} ({score:.0f}%), пережило {len(survived)}")
    if survived:
        print("ПЕРЕЖИВШИЕ (дыры в оракулах — это и есть находки; подтверждать чтением тестов):")
        for name in survived:
            print(f"  - {name}")
    for name, why in skipped:
        print(f"  (пропущен {name}: {why})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))