"""Бенчмарк ключевых путей spend-tracker на синтетике: замеры вместо догадок.

Зачем: при росте БД (5K → 50K+ операций) узкие места надо находить фактами. Скрипт
создаёт temp-БД (прод не трогает), сеет детерминированную синтетическую историю и меряет
median-время ключевых путей: страницы `/` и `/dashboard`, агрегаты отчётов, дайджест,
рекурринги, список/экспорт, а также `import_csv` на сгенерированной выписке Сбера.

Использование:
    uv run python scripts/bench.py run [--sizes 5000,20000,50000] [--repeats 3]
                                       [--import-rows 5000] [--skip-http] [--keep]
                                       [--out reports/bench.json]

Результат: таблица median-времён (мс) в stdout + JSON в `reports/bench.json` (по умолчанию).
HTTP-замеры — через TestClient (in-process, без реальной сети и портов).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "reports" / "bench.json"
SEED = 20260921
MONTHS = 36

# (категория, вес, min, max) — суммы в копейках; income положительный.
CATEGORIES: tuple[tuple[str, int, int, int], ...] = (
    ("groceries", 30, 30_000, 450_000),
    ("restaurants", 12, 20_000, 250_000),
    ("transport", 10, 6_000, 90_000),
    ("household", 8, 15_000, 120_000),
    ("fuel", 5, 150_000, 400_000),
    ("health", 4, 30_000, 300_000),
    ("entertainment", 4, 20_000, 200_000),
    ("clothes", 3, 50_000, 500_000),
    ("services", 3, 20_000, 300_000),
    ("other", 3, 10_000, 150_000),
    ("transfers", 3, 100_000, 1_000_000),
    ("income", 5, 5_000_000, 8_000_000),
)

MERCHANTS: dict[str, tuple[str, ...]] = {
    "groceries": ("ЛЕНТА", "МАГНИТ", "ПЯТЁРОЧКА", "ПЕРЕКРЁСТОК", "ВКУСВИЛЛ", "АШАН"),
    "restaurants": ("ВКУСНО И ТОЧКА", "КАФЕ МОЛОКО", "ШОКОЛАДНИЦА", "ДОДО ПИЦЦА", "КОФЕ-ПОИНТ"),
    "transport": ("ЯНДЕКС ТАКСИ", "МЕТРО", "САМОКАТ", "АЭРОЭКСПРЕСС"),
    "household": ("МАГАЗИН 1000 МЕЛОЧЕЙ", "ХОЗТОВАРЫ", "FIX PRICE", "ЛЕРУА МЕРЛЕН"),
    "fuel": ("АЗС ЛУКОЙЛ", "ГАЗПРОМНЕФТЬ", "АЗС ТАТНЕФТЬ"),
    "health": ("АПТЕКА 36.6", "РИГЛА", "КЛИНИКА СЕМЕЙНАЯ"),
    "entertainment": ("КИНО ОКТЯБРЬ", "МУЗЕЙ", "STEAM", "КОНЦЕРТ ХОЛЛ"),
    "clothes": ("СПОРТМАСТЕР", "ZARINA", "OZON ОДЕЖДА", "WILDBERRIES"),
    "services": ("РЕМОНТ КВАРТИР", "ХИМЧИСТКА", "ПАРИКМАХЕРСКАЯ", "КУРЬЕР"),
    "other": ("РАЗНОЕ", "КОМИССИЯ БАНКА", "ПРОЧЕЕ"),
    "transfers": ("ПЕРЕВОД СЕБЕ", "ПЕРЕВОД ДРУГУ"),
    "income": ("РАБОТОДАТЕЛЬ", "КЭШБЭК", "ПРОЦЕНТЫ ПО ВКЛАДУ"),
}

SUBSCRIPTIONS: tuple[tuple[str, str, int], ...] = (
    ("NETFLIX", "subscriptions", 19_900),
    ("YANDEX PLUS", "subscriptions", 39_900),
    ("SPOTIFY", "subscriptions", 19_900),
    ("MTS", "internet-phone", 65_000),
    ("IVI", "subscriptions", 29_900),
    ("YOUTUBE PREMIUM", "subscriptions", 19_900),
)

PENDING_ROWS = 200
CURRENCIES = ("RUB", "RUB", "RUB", "USDT", "USD", "EUR")


def seed(db_path: Path, n: int, months: int = MONTHS) -> dict:
    """Детерминированная синтетика: n операций за `months` месяцев, ~200 pending, бюджеты/examples.

    Вставка — одним executemany в одной транзакции (быстро); приложение для сева не используется,
    чтобы не платить за per-row commit. Возвращает факты о данных.
    """
    from spendtrack.store import Store, fingerprint

    store = Store(db_path=db_path)
    rng = random.Random(SEED + n)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=30 * months)
    span_days = (today - start).days

    rows: list[tuple] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    def add(day: date, desc: str, amount: int, category: str, merchant: str,
            currency: str = "RUB", source: str = "import", review: str = "approved",
            llm: str | None = None) -> None:
        fp = fingerprint(day.isoformat(), amount, desc, "acc_bench", str(len(rows)), currency)
        rows.append((day.isoformat(), desc, amount, currency, category, source, 1.0,
                     merchant, "acc_bench", None, fp, now, now, llm, review, len(rows)))

    # подписки: ежемесячные списания с фиксированным днём (для recurring-детектора)
    for month_shift in range(months):
        first = (start + timedelta(days=30 * month_shift)).replace(day=1)
        for idx, (merchant, category, amount) in enumerate(SUBSCRIPTIONS):
            day = first + timedelta(days=4 + idx)
            if start <= day <= today:
                delta = int(amount * 0.02 * rng.uniform(-0.5, 0.5))
                add(day, merchant, -(amount + delta), category, merchant)

    # зарплата 10-го и 25-го
    for month_shift in range(months):
        first = (start + timedelta(days=30 * month_shift)).replace(day=1)
        for dom in (10, 25):
            day = first + timedelta(days=dom - 1)
            if start <= day <= today:
                add(day, "ЗАРАБОТНАЯ ПЛАТА", rng.randint(6_500_000, 7_500_000), "income",
                    "РАБОТОДАТЕЛЬ")

    weights = [w for _, w, _, _ in CATEGORIES]
    cats = [(c, lo, hi) for c, _, lo, hi in CATEGORIES]
    remaining = max(0, n - len(rows))
    for i in range(remaining):
        category, lo, hi = rng.choices(cats, weights=weights, k=1)[0]
        amount = rng.randint(lo, hi)
        negative = category != "income"
        day = start + timedelta(days=rng.randint(0, span_days))
        merchant = rng.choice(MERCHANTS[category])
        desc = f"{merchant} {rng.choice(('МОСКВА', 'САНКТ-ПЕТЕРБУРГ', 'ОНЛАЙН', ''))}".strip()
        currency = rng.choice(CURRENCIES)
        add(day, desc, -amount if negative else amount, category, merchant, currency=currency)

    # очередь подтверждения: последние PENDING_ROWS — pending с предложением LLM
    for i in range(min(PENDING_ROWS, len(rows))):
        idx = len(rows) - 1 - i
        row = list(rows[idx])
        row[5], row[13], row[14] = "llm", "other", "pending"
        rows[idx] = tuple(row)

    conn = store.conn
    conn.executemany(
        "INSERT INTO transactions(date, description, amount_kopecks, currency, category,"
        " category_source, confidence, merchant, account_anon, import_batch, fingerprint,"
        " created, updated, category_llm, review_status, statement_order)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()

    for category, amount in (("groceries", 6_000_000), ("restaurants", 2_500_000),
                             ("transport", 1_000_000), ("household", 800_000),
                             ("fuel", 700_000)):
        store.set_budget(category, amount)
    for i in range(8):
        store.add_example(f"МАГАЗИН {i}", -(10_000 + i * 500), "groceries")
    for merchant in ("ЛЕНТА", "МАГНИТ", "ПЯТЁРОЧКА", "ЯНДЕКС ТАКСИ", "АПТЕКА 36.6"):
        store.merchant_cache_set(merchant, "groceries")

    facts = {
        "n_requested": n,
        "n_transactions": len(rows),
        "months": months,
        "pending": PENDING_ROWS,
        "db_bytes": db_path.stat().st_size,
    }
    store.close()
    return facts


def _gen_sber_csv(rows: int, seed: int = SEED) -> str:
    """Синтетическая выписка Сбера (валидные обязательные колонки, статус OK)."""
    rng = random.Random(seed)
    cats = [(c, lo, hi) for c, _, lo, hi in CATEGORIES if c != "income"]
    lines = ["Тип операции;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;Описание"]
    today = datetime.now(UTC).date()
    for i in range(rows):
        day = today - timedelta(days=rng.randint(0, 29))
        category, lo, hi = rng.choice(cats)
        amount = rng.randint(lo, hi)
        desc = f"{rng.choice(MERCHANTS[category])} ОПЛАТА {i}"
        amount_s = f"-{amount // 100},{amount % 100:02d}"
        lines.append(f"Списание;{day.strftime('%d.%m.%Y')};2202 20** **** 1234;OK;"
                     f"{amount_s};RUB;{desc}")
    return "\n".join(lines)


def _stub_classify(tx: dict, store, taxonomy) -> dict:
    """Без LLM/сети: правила не считаем — меряем импортный конвейер, а не категоризатор."""
    return {
        "category": "other",
        "source": "rule",
        "confidence": 1.0,
        "merchant": tx["description"][:24],
        "review_status": "approved",
        "category_llm": None,
    }


def _median_ms(fn, repeats: int) -> tuple[float, list[float]]:
    times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times), times


def _import_case(rows: int, repeats: int) -> dict:
    from spendtrack.csv_import import import_csv
    from spendtrack.store import Store

    csv_text = _gen_sber_csv(rows)
    times: list[float] = []
    result: dict = {}
    for _ in range(repeats):
        with tempfile.TemporaryDirectory(prefix="bench-import-") as tmp:
            db_path = Path(tmp) / "bench.db"
            store = Store(db_path=db_path)
            t0 = time.perf_counter()
            result = import_csv(csv_text, store, bank="sber", classify=_stub_classify)
            times.append((time.perf_counter() - t0) * 1000)
            store.close()
    median = statistics.median(times)
    return {
        "rows": rows,
        "median_ms": median,
        "runs_ms": times,
        "rows_per_second": round(rows / (median / 1000)) if median else None,
        "added": result.get("added"),
    }


def _http_cases(db_path: Path, repeats: int) -> dict:
    """median-время рендера страниц через TestClient (in-process).

    Роутеры создают Store() без аргумента, поэтому путь задаётся env-переменной (локально,
    в temp-БД скрипта; прод не задет).
    """
    os.environ["SPENDTRACK_DB_PATH"] = str(db_path)
    from fastapi.testclient import TestClient

    from spendtrack.main import app

    client = TestClient(app)
    out: dict = {}
    for path in ("/", "/dashboard"):
        client.get(path)  # warmup: импорт шаблонов, кэши sqlite
        median, times = _median_ms(lambda p=path: client.get(p), repeats)
        out[path] = {"median_ms": median, "runs_ms": times}
    return out


def run(args: argparse.Namespace) -> dict:
    from spendtrack.digest import build_digest
    from spendtrack.export import csv_bytes
    from spendtrack.recurring import detect_recurring
    from spendtrack.reports import (
        budgets_progress,
        categories_with_totals,
        report_daily,
        report_month,
    )
    from spendtrack.store import Store

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    tmp_root = Path(tempfile.mkdtemp(prefix="bench-spendtrack-"))
    report: dict = {
        "seed": SEED,
        "repeats": args.repeats,
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "sizes": {},
        "import": None,
    }
    try:
        for n in sizes:
            db_path = tmp_root / f"bench-{n}.db"
            facts = seed(db_path, n)
            store = Store(db_path=db_path)
            last_month = store.conn.execute(
                "SELECT MAX(date) m FROM transactions").fetchone()["m"][:7]

            cases = {
                "has_transactions (pages)": store.has_transactions,
                "counts (doctor)": store.counts,
                "queued_for_review": store.queued_for_review,
                "list_transactions_days (month)": lambda s=store, m=last_month: (
                    s.list_transactions_days(month=m)),
                "report_month": lambda s=store, m=last_month: report_month(s, m),
                "report_daily": lambda s=store, m=last_month: report_daily(s, m),
                "categories_with_totals": lambda s=store, m=last_month: (
                    categories_with_totals(s, m)),
                "budgets_progress": lambda s=store, m=last_month: budgets_progress(s, m),
                "detect_recurring": lambda s=store: detect_recurring(s),
                "build_digest": lambda s=store: build_digest(s),
                "export_transactions + csv": lambda s=store: csv_bytes(s.export_transactions()),
            }
            size_out: dict = {"facts": facts, "cases": {}}
            for name, fn in cases.items():
                median, times = _median_ms(fn, args.repeats)
                size_out["cases"][name] = {"median_ms": median, "runs_ms": times}
            if not args.skip_http:
                try:
                    size_out["http"] = _http_cases(db_path, args.repeats)
                except Exception as exc:  # noqa: BLE001 — http-замер не должен ронять остальные
                    size_out["http"] = {"error": f"{type(exc).__name__}: {exc}"}
            report["sizes"][str(n)] = size_out
            store.close()
    finally:
        if args.keep:
            print(f"[bench] temp: {tmp_root}", flush=True)
        else:
            shutil.rmtree(tmp_root, ignore_errors=True)

    if args.import_rows:
        report["import"] = _import_case(args.import_rows, args.repeats)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _print_report(report: dict) -> None:
    sizes = list(report["sizes"])
    names: list[str] = []
    for size in report["sizes"].values():
        for name in size["cases"]:
            if name not in names:
                names.append(name)
        for name in size.get("http", {}):
            key = f"HTTP {name}"
            if key not in names and "median_ms" in size["http"][name]:
                names.append(key)

    width = max(len(name) for name in names) + 2
    header = "case".ljust(width) + "".join(f"{s:>12}" for s in sizes)
    print(header)
    print("-" * len(header))
    for name in names:
        cells = []
        for size in sizes:
            data = report["sizes"][size]
            if name.startswith("HTTP "):
                entry = data.get("http", {}).get(name[5:], {})
            else:
                entry = data["cases"].get(name, {})
            median = entry.get("median_ms")
            cells.append(f"{median:>12.1f}" if median is not None else f"{'-':>12}")
        print(name.ljust(width) + "".join(cells))
    print("(median, мс)")
    if report.get("import"):
        imp = report["import"]
        print(f"import_csv sber: {imp['rows']} строк → {imp['median_ms']:.0f} мс"
              f" ({imp['rows_per_second']} строк/с), added={imp['added']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Бенчмарк spend-tracker на синтетике (temp-БД)")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="сеять синтетику и мерить")
    run_p.add_argument("--sizes", default="5000,20000,50000",
                       help="размеры истории (строк через запятую)")
    run_p.add_argument("--repeats", type=int, default=3)
    run_p.add_argument("--import-rows", type=int, default=5000,
                       help="строк в синтетической выписке для import_csv (0 — пропустить)")
    run_p.add_argument("--skip-http", action="store_true")
    run_p.add_argument("--keep", action="store_true", help="не удалять temp-БД (для разбора)")
    run_p.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    if args.command == "run":
        report = run(args)
        _print_report(report)
        print(f"\nJSON: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
