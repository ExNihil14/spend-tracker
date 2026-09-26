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
                                   taxonomy=taxonomy, filename="ratchet.csv")
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


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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


def _cmd_check(as_json: bool) -> int:
    failures: list[str] = []
    baseline: dict = {}
    try:
        baseline = load_baseline(BASELINE_PATH)
    except (OSError, ValueError) as e:
        failures.append(f"базлайн недоступен или битый ({BASELINE_PATH.name}): {e} — гейт не может сработать")
    if baseline and baseline.get("version") != 1:
        failures.append(
            f"базлайн: неизвестная версия схемы {baseline.get('version')!r} (ожидается 1) — гейт не может сработать"
        )
    current: dict = {}
    try:
        current = measure()
    except AssertionError as e:
        failures.append(f"замер не сработал: {e}")
    if baseline:
        failures += compare(baseline, current)
    if as_json:
        print(json.dumps({"baseline": baseline.get("metrics"), "current": current, "failures": failures},
                         ensure_ascii=False, indent=2))
    else:
        print("Ratchet-метрики (только вниз; время — инфо):")
        metrics = baseline.get("metrics") or {}
        for metric, limit in GATES.items():
            print(f"  {metric:<22} текущее {_fmt_num(current.get(metric))}  "
                  f"базлайн {_fmt_num(metrics.get(metric))}  гейт ×{limit}")
        print(f"  {'categorize_100_ms':<22} текущее {_fmt_num(current.get('categorize_100_ms'))}  "
              f"базлайн {_fmt_num(metrics.get('categorize_100_ms'))}  (инфо)")
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
