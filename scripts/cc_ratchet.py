"""Ratchet-гейт цикломатической сложности (ruff C901) — «только вниз».

Зачем: обычный `C901` (порог 10) нельзя включить без правок — 5 legacy-функций сложнее 10; `# noqa: C901`
без контроля позволяет функции расти незаметно (ревью Opus 5.5, 27.09). Решение: ruff C901 включён
(`extend-select`), legacy-функции помечены `noqa`, а этот скрипт через `--ignore-noqa` видит реальные числа
и сравнивает с `spec/cc_baseline.json`:
- рост сложности или новая функция > порога → FAIL;
- снижение/исправление → подсказка запустить `update`;
- `update` понижает свободно; новые функции > порога и рост существующих — только с `--force`
  (осознанное принятие долга; согласуется с `ratchet.py snapshot --force`).

Использование:
    uv run python scripts/cc_ratchet.py check     # CI
    uv run python scripts/cc_ratchet.py update    # переснять baseline (понижение — свободно)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "spec" / "cc_baseline.json"
COMPLEX_RE = re.compile(r"`(?P<name>[^`]+)` is too complex \((?P<value>\d+) > \d+\)")

if hasattr(sys.stdout, "reconfigure"):  # редирект в cp1251-лог не должен ронять печать (стрелки и т.п.)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_c901(payload: list[dict]) -> dict[str, int]:
    """JSON-вывод `ruff check --select C901 --ignore-noqa` → {путь::функция: сложность}."""
    out: dict[str, int] = {}
    for entry in payload:
        if entry.get("code") != "C901":
            continue
        match = COMPLEX_RE.search(entry.get("message", ""))
        if not match:
            continue
        try:
            rel = Path(entry["filename"]).resolve().relative_to(ROOT).as_posix()
        except (KeyError, ValueError):  # файл вне репо (симлинк/подмодуль) — не наш объект
            print(f"cc ratchet: WARN — пропускаю файл вне репо: {entry.get('filename')}", flush=True)
            continue
        out[f"{rel}::{match.group('name')}"] = int(match.group("value"))
    return out


def parse_or_fail(payload: list[dict]) -> dict[str, int]:
    """Fail-closed: если ruff сообщил C901, а мы не разобрали — это дрейф формата, а не «всё хорошо»."""
    parsed = parse_c901(payload)
    reported = sum(1 for entry in payload if entry.get("code") == "C901")
    if reported != len(parsed):
        raise SystemExit(
            f"cc ratchet: FAIL — разобрано {len(parsed)} из {reported} сообщений C901 "
            "(дрейф формата ruff? обнови COMPLEX_RE в scripts/cc_ratchet.py)")
    return parsed


def compare(current: dict[str, int], baseline: dict[str, int]) -> tuple[list[str], list[str]]:
    """→ (failures, notes): рост/новые — FAIL; снижение/исчезновение — note (запустить update)."""
    fails: list[str] = []
    notes: list[str] = []
    for key, value in sorted(current.items()):
        base = baseline.get(key)
        if base is None:
            fails.append(f"новая функция сложнее порога: {key} = {value}")
        elif value > base:
            fails.append(f"сложность выросла: {key}: {base} → {value}")
        elif value < base:
            notes.append(f"сложность снизилась: {key}: {base} → {value} — запусти `update`")
    for key in sorted(set(baseline) - set(current)):
        notes.append(f"запись неактуальна (функция исправлена/переименована): {key} — запусти `update`")
    return fails, notes


def raised(current: dict[str, int], baseline: dict[str, int]) -> dict[str, tuple[int | None, int]]:
    """Записи, которые `update` без --force повышать не станет."""
    out: dict[str, tuple[int | None, int]] = {}
    for key, value in current.items():
        base = baseline.get(key)
        if base is None or value > base:
            out[key] = (base, value)
    return out


def run_ruff() -> list[dict]:
    ruff = shutil.which("ruff")
    cmd = ([ruff] if ruff else ["uv", "run", "ruff"]) + [
        "check", "--select", "C901", "--ignore-noqa", "--output-format", "json", "."]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if result.returncode not in (0, 1):  # ruff: 1 = есть находки (это ожидаемо)
        raise SystemExit(f"ruff не отработал (rc={result.returncode}): {result.stderr[:300]}")
    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"не разобрал JSON ruff: {exc}") from exc


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        raise SystemExit("нет spec/cc_baseline.json — запусти `uv run python scripts/cc_ratchet.py update`")
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in (data.get("functions") or {}).items()}


def save_baseline(functions: dict[str, int]) -> None:
    BASELINE.write_text(
        json.dumps({"schema": 1, "functions": dict(sorted(functions.items()))},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ratchet цикломатической сложности (ruff C901)")
    parser.add_argument("cmd", choices=("check", "update"))
    parser.add_argument("--force", action="store_true", help="разрешить повышение baseline (осознанно)")
    args = parser.parse_args(argv)

    current = parse_or_fail(run_ruff())
    if args.cmd == "update":
        old = load_baseline() if BASELINE.exists() else {}
        grows = raised(current, old)
        if grows and not args.force:
            print("cc ratchet: отказ — повышение baseline без --force (осознанное принятие долга):")
            for key, (base, value) in sorted(grows.items()):
                where = "новая функция > порога" if base is None else "рост существующей"
                print(f"  {where}: {key}: {base} → {value}")
            print("  варианты: отрефакторить функцию до ≤10 или повторить `update --force` "
                  "(в коммите — трейлер Contract-Change)")
            return 1
        save_baseline(current)
        print(f"cc ratchet: baseline обновлён ({len(current)} функций > порога) → {BASELINE.name}")
        return 0

    fails, notes = compare(current, load_baseline())
    for note in notes:
        print(f"cc ratchet: note — {note}")
    if fails:
        print("cc ratchet: FAIL")
        for fail in fails:
            print(f"  {fail}")
        return 1
    print(f"cc ratchet: ok ({len(current)} функций в baseline, роста нет)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
