"""Ratchet-метрики (M10): детерминированные счётчики работы с БД с порогом «только вниз».

Принцип «сначала падающий бенчмарк, потом оптимизация»: метрика закрепляется на текущем значении,
любой рост — красный CI (рядом с contract-дельтой). Базлайн — `spec/ratchet_baseline.json`,
обновляется только `snapshot`; повышение записанного значения требует `--force` (осознанное решение).

Ложные гарантии закрыты (§J-2): нет метрики/не число в базлайне или замере, битый базлайн,
неизвестная версия и упавший `measure()` — FAIL; «слишком хорошо» (0 или < 0.5×базлайна) — FAIL.
F2 (адъюдикация wave8, `gates`): битым считается и базлайн, который прочитался, но оказался НЕ
объектом (`null`): раньше проверка типа шла только при `baseline is not None`, поэтому `null`
проходил как «базлайна нет» — `check --json` давал rc=0 с пустым `failures`, а текстовый режим
падал на `.get()`. `guard` (CI, PR) ловит рост базлайна против базовой ветки — обход
`snapshot --force` невозможен без метки `ratchet-raise` в PR. В снимок пишутся версии окружения
(python/sqlite), при расхождении с базлайном `check` печатает WARN (метрика может сдвинуться от
смены версий, а не кода).

Метрики:
  report_month_queries — SQL-запросов на месячный отчёт (стоимость страницы /).
  import_100_queries   — SQL-запросов на импорт 100 строк выписки.
  categorize_100_ms    — медиана мс на 100 правил-категоризаций (машино-зависимо: пишется в снимок
                         для тренда, в гейт не входит; LLM исключён — детерминизм).

Запуск:
  uv run python scripts/ratchet.py check [--json]
  uv run python scripts/ratchet.py snapshot [--force]
  uv run python scripts/ratchet.py guard --base origin/main   # рост базлайна против ветки — FAIL
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "spec" / "ratchet_baseline.json"
BASELINE_REL = "spec/ratchet_baseline.json"  # путь в git-дереве (для `git show <ref>:…`)

# Гейт: во сколько раз допустимо превысить записанное значение (1.0 = «только вниз»).
# Время не гейтится (машино-зависимо, флейки в CI) — пишется в снимок для тренда.
GATES = {
    "report_month_queries": 1.0,
    "import_100_queries": 1.0,
}

# Параметры замера — часть контракта метрики: ассерты в measure() ловят их изменение
# (уменьшил seed/строки импорта — метрика «улучшилась» без улучшения кода).
SEED_MONTHS = 12
SEED_PER_MONTH = 40
IMPORT_ROWS = 100


class QueryCounter:
    """Счётчик выполненных SQL-операторов через sqlite3 trace callback."""

    def __init__(self, conn) -> None:
        self.count = 0
        conn.set_trace_callback(self._tick)

    def _tick(self, _statement: str) -> None:
        self.count += 1

    def reset(self) -> None:
        self.count = 0


def _seed(store, months: int = SEED_MONTHS, per_month: int = SEED_PER_MONTH) -> None:
    """Детерминированные данные: 12 месяцев, 40 операций в месяц, фиксированные суммы/мерчанты."""
    for month in range(1, months + 1):
        for i in range(per_month):
            day = 1 + (i % 27)
            store.add_transaction(
                date=f"2026-{month:02d}-{day:02d}",
                description=f"МЕРЧАНТ-{i % 17} покупка",
                amount_kopecks=-((i * 137) % 9000 + 100),
                category="household" if i % 2 else "groceries",
                category_source="rule",
                merchant=f"МЕРЧАНТ-{i % 17}",
                account_anon="acc_ratchet",
                export_rowid="",
                commit=False,
            )
    store.conn.commit()


def _gen_sber_email(n: int = 100, seed: int = 7) -> str:
    """Синтетическая выписка из общего генератора тестов (единый источник формы Сбера)."""
    import importlib.util

    path = ROOT / "tests" / "synth_bank.py"
    spec = importlib.util.spec_from_file_location("ratchet_synth_bank", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.gen_sber_email(n=n, seed=seed)


def _offline_classify(tx: dict, store, taxonomy) -> dict:
    """S3 (адъюдикация 29.09): детерминированный классификатор замера — без сети.

    Раньше classify не передавался: боевой categorize_transaction при ключах в env уходил
    в LLM-шов (сеть, минуты, другие счётчики), в CI — в офлайн-фолбэк; метрика зависела от env.
    Правило → категория, иначе «other» в очередь (та же форма, что у тестового стаба).
    """
    from spendtrack.categorize import categorize_rules_only

    rule = categorize_rules_only(tx, taxonomy, store)
    if rule:
        return {"category": rule, "confidence": 1.0, "merchant": tx.get("merchant"),
                "reason": "rule", "source": "rule"}
    return {"category": "other", "confidence": 0.5, "merchant": tx.get("merchant"),
            "reason": "ratchet_stub", "source": "llm_pending_review"}


def measure() -> dict[str, float]:
    """Снять все метрики на изолированной temp-БД. Прод не трогает.

    Ассерты-инварианты: без реальной работы счётчики SQL падают (упавший импорт = меньше
    запросов), а гейт «только вниз» наградил бы поломку. Замер с пустым результатом невалиден.
    """
    from spendtrack.categorize import categorize_rules_only
    from spendtrack.csv_import import import_csv
    from spendtrack.reports import report_month
    from spendtrack.store import Store
    from spendtrack.taxonomy import load_taxonomy

    taxonomy = load_taxonomy(ROOT / "config")

    with tempfile.TemporaryDirectory(prefix="ratchet-") as tmp:
        store = Store(db_path=Path(tmp) / "ratchet.db")
        try:
            _seed(store)
            seeded = store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            assert seeded == SEED_MONTHS * SEED_PER_MONTH, (
                f"seed: ожидалось {SEED_MONTHS * SEED_PER_MONTH} строк, в БД {seeded} — замер отброшен"
            )
            counter = QueryCounter(store.conn)

            counter.reset()
            report = report_month(store, "2026-06")
            report_queries = counter.count
            assert report["expense_k"] != 0, "отчёт за 2026-06 пуст — замер отброшен"

            counter.reset()
            imported = import_csv(_gen_sber_email(IMPORT_ROWS, 7), store, bank="auto",
                                   taxonomy=taxonomy, classify=_offline_classify, filename="ratchet.csv")
            import_queries = counter.count
            # 104 строки в синтетике: 100 базовых + зарплата/возврат/дубль в день/«В обработке»
            # (email-CSV статуса не имеет, поэтому приняты все).
            assert imported.get("status") == "ok" and imported.get("added") == IMPORT_ROWS + 4, (
                f"импорт: status={imported.get('status')!r}, added={imported.get('added')!r}"
                f" (ожидалось 'ok'/{IMPORT_ROWS + 4}) — замер отброшен"
            )

            txs = [
                {
                    "date": "2026-06-01",
                    "description": f"МЕРЧАНТ-{i % 17} покупка",
                    "amount_kopecks": -((i * 137) % 9000 + 100),
                    "currency": "RUB",
                }
                for i in range(100)
            ]
            samples: list[float] = []
            for i in range(4):  # 1 прогрев + 3 замера (первый прогон холодный)
                started = time.perf_counter()
                for tx in txs:
                    categorize_rules_only(tx, taxonomy, store)
                if i:
                    samples.append((time.perf_counter() - started) * 1000)
        finally:
            store.conn.set_trace_callback(None)
            store.close()

    return {
        "report_month_queries": report_queries,
        "import_100_queries": import_queries,
        "categorize_100_ms": round(statistics.median(samples), 3),
    }


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def env_info() -> dict[str, str]:
    """Версии окружения, влияющие на счётчики SQL (§J-2): неявные BEGIN/COMMIT и sqlite-версия
    меняются между Python/SQLite — без фиксации сдвиг метрики не отличить от регрессии кода."""
    return {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": sys.platform}


def load_baseline_from_ref(ref: str) -> dict:
    """Ссылка на базлайн в git (CI: origin/main): `git show <ref>:spec/ratchet_baseline.json`."""
    result = subprocess.run(["git", "show", f"{ref}:{BASELINE_REL}"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise ValueError(f"не удалось прочитать базлайн из {ref}: {(result.stderr or '').strip()[:200]}")
    return json.loads(result.stdout)


def _is_number(value: object) -> bool:
    # S1 (Astra 01.10): NaN/бесконечности — не числа для гейта (сравнения с NaN всегда ложны,
    # из-за чего «только вниз» молча пропускал бы любые значения).
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compare(baseline: dict, current: dict, gates: dict | None = None) -> list[str]:
    """Вернуть список нарушений «только вниз» (пусто — всё в пределах гейта).

    Ложные гарантии — тоже нарушение: метрика, отсутствующая в базлайне или замере (или не число),
    означает, что гейт не может сработать, — это FAIL, а не молчаливый пропуск. Подозрительно
    низкое значение (0 или < 0.5×базлайна) — FAIL: так выглядит поломка замера, а не оптимизация.
    """
    gates = GATES if gates is None else gates
    failures: list[str] = []
    base_metrics = baseline.get("metrics") or {}
    current_metrics = current or {}
    for metric, limit in gates.items():
        base = base_metrics.get(metric)
        now = current_metrics.get(metric)
        if not _is_number(base):
            failures.append(
                f"{metric}: метрика отсутствует или не число в базлайне ({base!r}) — гейт не может сработать"
            )
            continue
        if not _is_number(now):
            failures.append(
                f"{metric}: метрика отсутствует или не число в замере ({now!r}) — гейт не может сработать"
            )
            continue
        if now > base * limit:
            failures.append(
                f"{metric}: {now} > {base} × {limit} (базлайн {base}) — рост метрики, CI-гейт «только вниз»"
            )
        elif now <= 0 or now < base * 0.5:
            failures.append(
                f"{metric}: {now} при базлайне {base} — «слишком хорошо» (< 0.5×базлайна): "
                "похоже на поломку замера, а не оптимизацию; осознанно — `snapshot`"
            )
    return failures


def _fmt_num(value: object, width: int = 8) -> str:
    """Число для текстового отчёта; не-число — «—» (текстовый режим не падает там, где --json даёт FAIL)."""
    return f"{value:>{width}}" if _is_number(value) else f"{'—':>{width}}"


def baseline_drift(base: dict, current: dict, gates: dict | None = None) -> list[str]:
    """Рост гейтируемых метрик в базлайне PR против базлайна базовой ветки (CI-гейт, §J-2).

    `snapshot --force` защищает только локальный запуск: в PR базлайн мог быть поднят вместе с кодом.
    Осознанный рост — метка `ratchet-raise` в PR (шаг CI пропускается). Пропажа метрики — тоже FAIL.
    """
    gates = GATES if gates is None else gates
    failures: list[str] = []
    base_metrics = base.get("metrics") or {}
    cur_metrics = current.get("metrics") or {}
    for metric in gates:
        old = base_metrics.get(metric)
        new = cur_metrics.get(metric)
        if not _is_number(old):
            continue  # в базовой ветке метрики нет — сверять нечего
        if not _is_number(new):
            failures.append(f"{metric}: метрика пропала из базлайна PR — гейт не сможет сработать")
        elif new > old:
            failures.append(f"{metric}: {old} → {new} — рост базлайна (осознанно — метка `ratchet-raise` в PR)")
    return failures


def env_warnings(baseline: dict, env: dict | None = None) -> list[str]:
    """Предупреждения о смене версий окружения против снимка (не FAIL: сдвиг объясняется версией)."""
    base_env = baseline.get("env") or {}
    env = env or env_info()
    out: list[str] = []
    for key in ("python", "sqlite"):
        if base_env.get(key) and env.get(key) and base_env[key] != env[key]:
            out.append(f"{key}: {base_env[key]} → {env[key]} — метрика может сдвинуться; "
                       "осознанно пере-снять `snapshot`")
    return out


def _baseline_structure_failures(baseline: dict) -> list[str]:
    """S1 (Astra 01.10): структура/версия базлайна — не через truthiness (`if baseline`).

    Пустой `{}` раньше «выключал» и проверку версии, и метрики; теперь версия проверяется всегда,
    а отсутствующие метрики ловит compare() (по FAIL на каждую).
    """
    if baseline.get("version") != 1:
        return [
            (
                f"базлайн: неизвестная версия схемы {baseline.get('version')!r} (ожидается 1)"
                " — гейт не может сработать"
            )
        ]
    return []


def _cmd_check(as_json: bool) -> int:
    failures: list[str] = []
    baseline: dict | None = None
    loaded = False
    try:
        baseline = load_baseline(BASELINE_PATH)
        loaded = True
    except (OSError, ValueError) as e:
        failures.append(f"базлайн недоступен или битый ({BASELINE_PATH.name}): {e} — гейт не может сработать")
    # F2 (адъюдикация wave8, `gates`): тип проверяем ВСЕГДА, включая None. JSON `null` проходит
    # `json.loads` как None, а условие `baseline is not None` отсекало и проверку типа, и
    # `_baseline_structure_failures`, и `compare()` — гейт молча переставал мерить. Теперь это FAIL.
    if loaded and not isinstance(baseline, dict):
        failures.append(f"базлайн: не объект JSON ({BASELINE_PATH.name}: {type(baseline).__name__})"
                        " — гейт не может сработать")
        baseline = None
    if baseline is not None:
        failures += _baseline_structure_failures(baseline)
    current: dict = {}
    try:
        current = measure()
    except AssertionError as e:
        failures.append(f"замер не сработал: {e}")
    if baseline is not None:
        failures += compare(baseline, current)
    env = env_info()
    warnings = env_warnings(baseline, env) if baseline is not None else []
    if as_json:
        print(json.dumps({"baseline": (baseline or {}).get("metrics"), "current": current, "failures": failures,
                          "env": env, "env_warnings": warnings},
                         ensure_ascii=False, indent=2))
    else:
        print("Ratchet-метрики (только вниз; время — инфо):")
        # `baseline or {}`: базлайн может быть непригоден (см. F2) — отчёт должен печатать FAIL,
        # а не падать AttributeError на `None.get(...)`.
        metrics = (baseline or {}).get("metrics") or {}
        for metric, limit in GATES.items():
            print(f"  {metric:<22} текущее {_fmt_num(current.get(metric))}  "
                  f"базлайн {_fmt_num(metrics.get(metric))}  гейт ×{limit}")
        print(f"  {'categorize_100_ms':<22} текущее {_fmt_num(current.get('categorize_100_ms'))}  "
              f"базлайн {_fmt_num(metrics.get('categorize_100_ms'))}  (инфо)")
        for warning in warnings:
            print(f"  ВНИМАНИЕ {warning}")
        for failure in failures:
            print(f"  FAIL {failure}")
    return 1 if failures else 0


def _cmd_snapshot(force: bool) -> int:
    old = load_baseline() if BASELINE_PATH.is_file() else {"metrics": {}}
    current = measure()
    # «Только вниз» — для гейтируемых счётчиков; время информационно и обновляется всегда.
    raised = [
        metric
        for metric in GATES
        if metric in old.get("metrics", {}) and current.get(metric, 0) > old["metrics"][metric]
    ]
    if raised and not force:
        print(f"snapshot отказ: рост метрик {raised} — допустимо только вниз; осознанно — `--force`")
        return 2
    payload = {"version": 1, "measured_at": time.strftime("%Y-%m-%d"), "env": env_info(),
               "metrics": current}
    BASELINE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shown = BASELINE_PATH.relative_to(ROOT) if BASELINE_PATH.is_relative_to(ROOT) else BASELINE_PATH
    print(f"snapshot: {shown} ← {current}")
    return 0


def _cmd_guard(base_ref: str) -> int:
    """CI-гейт: базлайн PR не выше базлайна базовой ветки (кроме метки `ratchet-raise` в PR)."""
    try:
        base = load_baseline_from_ref(base_ref)
    except (OSError, ValueError) as e:
        print(f"guard: {e}", file=sys.stderr, flush=True)
        return 2
    try:
        current = load_baseline(BASELINE_PATH)
    except (OSError, ValueError) as e:
        print(f"guard: базлайн PR не прочитан ({BASELINE_PATH.name}): {e}", file=sys.stderr, flush=True)
        return 2
    failures = baseline_drift(base, current)
    if failures:
        print(f"ratchet guard: базлайн вырос против {base_ref}:")
        for failure in failures:
            print(f"  FAIL {failure}")
        return 1
    print(f"ratchet guard: базлайн не вырос против {base_ref} — ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    from spendtrack.console import utf8_stdout

    utf8_stdout()
    parser = argparse.ArgumentParser(description="Ratchet-метрики (порог «только вниз»)")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="снять метрики и сверить с базлайном")
    check.add_argument("--json", action="store_true")
    snap = sub.add_parser("snapshot", help="обновить базлайн измерениями (рост — только с --force)")
    snap.add_argument("--force", action="store_true")
    guard = sub.add_parser("guard", help="CI: базлайн PR не выше базлайна ветки (--base origin/main)")
    guard.add_argument("--base", required=True, metavar="REF",
                       help="git-ссылка базовой ветки (например, origin/main)")
    args = parser.parse_args(argv)

    if args.command == "check":
        return _cmd_check(args.json)
    if args.command == "guard":
        return _cmd_guard(args.base)
    return _cmd_snapshot(args.force)


if __name__ == "__main__":
    sys.exit(main())
