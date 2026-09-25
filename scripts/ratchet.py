"""Ratchet-метрики (M10): детерминированные счётчики работы с БД с порогом «только вниз».

Принцип «сначала падающий бенчмарк, потом оптимизация»: метрика закрепляется на текущем значении,
любой рост — красный CI (рядом с contract-дельтой). Базлайн — `spec/ratchet_baseline.json`,
обновляется только `snapshot`; повышение записанного значения требует `--force` (осознанное решение).

Метрики:
  report_month_queries — SQL-запросов на месячный отчёт (стоимость страницы /).
  import_100_queries   — SQL-запросов на импорт 100 строк выписки.
  categorize_100_ms    — медиана мс на 100 правил-категоризаций (машино-зависимо: пишется в снимок
                         для тренда, в гейт не входит; LLM исключён — детерминизм).

Запуск:
  uv run python scripts/ratchet.py check [--json]
  uv run python scripts/ratchet.py snapshot [--force]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "spec" / "ratchet_baseline.json"

# Гейт: во сколько раз допустимо превысить записанное значение (1.0 = «только вниз»).
# Время не гейтится (машино-зависимо, флейки в CI) — пишется в снимок для тренда.
GATES = {
    "report_month_queries": 1.0,
    "import_100_queries": 1.0,
}


class QueryCounter:
    """Счётчик выполненных SQL-операторов через sqlite3 trace callback."""

    def __init__(self, conn) -> None:
        self.count = 0
        conn.set_trace_callback(self._tick)

    def _tick(self, _statement: str) -> None:
        self.count += 1

    def reset(self) -> None:
        self.count = 0


def _seed(store, months: int = 12, per_month: int = 40) -> None:
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


def measure() -> dict[str, float]:
    """Снять все метрики на изолированной temp-БД. Прод не трогает."""
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
            counter = QueryCounter(store.conn)

            counter.reset()
            report_month(store, "2026-06")
            report_queries = counter.count

            counter.reset()
            import_csv(_gen_sber_email(100, 7), store, bank="auto", taxonomy=taxonomy, filename="ratchet.csv")
            import_queries = counter.count

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


def compare(baseline: dict, current: dict, gates: dict | None = None) -> list[str]:
    """Вернуть список нарушений «только вниз» (пусто — всё в пределах гейта)."""
    gates = gates or GATES
    failures: list[str] = []
    for metric, limit in gates.items():
        base = baseline.get("metrics", {}).get(metric)
        now = current.get(metric)
        if base is None or now is None:
            continue
        if now > base * limit:
            failures.append(
                f"{metric}: {now} > {base} × {limit} (базлайн {base}) — рост метрики, CI-гейт «только вниз»"
            )
    return failures


def _cmd_check(as_json: bool) -> int:
    baseline = load_baseline()
    current = measure()
    failures = compare(baseline, current)
    if as_json:
        print(json.dumps({"baseline": baseline.get("metrics"), "current": current, "failures": failures},
                         ensure_ascii=False, indent=2))
    else:
        print("Ratchet-метрики (только вниз; время — инфо):")
        for metric in ("report_month_queries", "import_100_queries"):
            base = baseline.get("metrics", {}).get(metric)
            print(f"  {metric:<22} текущее {current.get(metric):>8}  базлайн {base:>8}  гейт ×{GATES[metric]}")
        base_ms = baseline.get("metrics", {}).get("categorize_100_ms")
        print(f"  {'categorize_100_ms':<22} текущее {current.get('categorize_100_ms'):>8}  "
              f"базлайн {base_ms:>8}  (инфо)")
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
    payload = {"version": 1, "measured_at": time.strftime("%Y-%m-%d"), "metrics": current}
    BASELINE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"snapshot: {BASELINE_PATH.relative_to(ROOT)} ← {current}")
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
    args = parser.parse_args(argv)

    if args.command == "check":
        return _cmd_check(args.json)
    return _cmd_snapshot(args.force)


if __name__ == "__main__":
    sys.exit(main())
