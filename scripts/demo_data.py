"""Демо-режим: синтетические данные для витрины всех фич (детерминированно, безопасно).

Профиль «полная витрина»: ~5 месяцев, 12+ категорий, доходы, подписки (включая скачок цены),
аномалия крупной суммы, near-дубль, очередь на подтверждение, правки/examples/merchant_cache,
бюджеты (перерасход и ~80%), партия импорта.

Использование:
    uv run python scripts/demo_data.py seed [--if-empty] [--force] [--verify] [--db data/demo.db]
    uv run python scripts/demo_data.py status [--db data/demo.db]
    uv run python scripts/demo_data.py clean  [--db data/demo.db]

Демо-стенд: SPENDTRACK_DB_PATH=data/demo.db uv run uvicorn spendtrack.main:app --port 8767
Реальная БД не затрагивается, если явно не указать её через --db (и тогда потребуется --force).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, date, datetime, timedelta
from itertools import count
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "demo.db"
SEED = 20260919
DAYS = 150
PENDING_COUNT = 6


def manifest_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + ".demo_manifest.json")


def _rnd_amount(rng: random.Random, lo: int, hi: int) -> int:
    return -rng.randint(lo, hi)


def _place(store, day: date, desc: str, amount: int, category: str, seq,
           source: str = "import", merchant: str | None = None, batch: str | None = None,
           category_llm: str | None = None, review_status: str = "approved",
           confidence: float = 1.0) -> None:
    store.add_transaction(
        date=day.isoformat(), description=desc, amount_kopecks=amount, category=category,
        category_source=source, confidence=confidence, merchant=merchant or desc[:24],
        import_batch=batch, export_rowid=f"demo{next(seq)}", category_llm=category_llm,
        review_status=review_status)


def build(store, today: date) -> dict:
    """Синтетическая история; возвращает {batch, fingerprints, budgets, examples, merchant_cache}."""
    rng = random.Random(SEED)
    seq = count(1)
    batch = store.add_batch("demo_seed.csv", "demo", 0)
    start = today - timedelta(days=DAYS)

    def add(day, desc, amount, cat, **kw):
        _place(store, day, desc, amount, cat, seq, batch=batch, **kw)

    # --- доходы: зарплата 10-го и 25-го ---
    for month_shift in range(6):
        base = (start + timedelta(days=30 * month_shift))
        for dom in (10, 25):
            day = base.replace(day=1) + timedelta(days=dom - 1)
            if start <= day <= today:
                add(day, "ЗАРАБОТНАЯ ПЛАТА", rng.randint(65000, 75000) * 100, "income",
                    merchant="РАБОТОДАТЕЛЬ")

    # --- подписки: 5 списаний по 30 дней (NETFLIX со скачком цены в окне) ---
    for desc, amount, cat, offsets in (
        ("NETFLIX", 19900, "subscriptions", (145, 115, 85, 55, 25)),
        ("YANDEX PLUS", 39900, "subscriptions", (140, 110, 80, 50, 20)),
        ("SPOTIFY", 19900, "subscriptions", (150, 120, 90, 60, 30)),
        ("MTS", 65000, "internet-phone", (135, 105, 75, 45, 15)),
    ):
        for off in offsets:
            add(today - timedelta(days=off), desc, -amount, cat, merchant=desc)
    add(today - timedelta(days=2), "NETFLIX", -25900, "subscriptions", merchant="NETFLIX")

    # --- регулярный быт (household ×2/нед — база для аномалии: >=10 наблюдений за 90 дней) ---
    for week in range(DAYS // 7):
        for _ in range(2):
            day = today - timedelta(days=DAYS - week * 7 - rng.randint(0, 3))
            if day <= today:
                name = rng.choice(("МАГАЗИН 1000 МЕЛОЧЕЙ", "ХОЗТОВАРЫ", "FIX PRICE"))
                add(day, f"{name} МОСКВА", _rnd_amount(rng, 15000, 90000), "household",
                    merchant=name)

    # --- продукты (3-4/нед) ---
    for week in range(DAYS // 7):
        for _ in range(rng.randint(3, 4)):
            day = today - timedelta(days=DAYS - week * 7 - rng.randint(0, 6))
            name = rng.choice(("ЛЕНТА", "МАГНИТ", "ПЯТЁРОЧКА", "ПЕРЕКРЁСТОК"))
            add(day, f"{name} СУПЕРМАРКЕТ", _rnd_amount(rng, 60000, 450000), "groceries",
                merchant=name)

    # --- транспорт/кафе/АЗС/кофе (витринная плотность), аптека/кино/одежда — по месяцам ---
    for week in range(DAYS // 7):
        for _ in range(2):
            name = rng.choice(("ЯНДЕКС ТАКСИ", "МЕТРО"))
            add(today - timedelta(days=DAYS - week * 7 - rng.randint(0, 6)),
                f"{name} ПОЕЗДКА", _rnd_amount(rng, 6000, 90000), "transport", merchant=name)
        for _ in range(2):
            name = rng.choice(("ВКУСНО И ТОЧКА", "КАФЕ МОЛОКО", "ШОКОЛАДНИЦА"))
            add(today - timedelta(days=DAYS - week * 7 - rng.randint(0, 6)),
                f"{name} МОСКВА", _rnd_amount(rng, 40000, 250000), "restaurants", merchant=name)
        for _ in range(2):
            add(today - timedelta(days=DAYS - week * 7 - rng.randint(0, 6)),
                "КОФЕ-ПОИНТ УГЛОВОЕ", _rnd_amount(rng, 12000, 35000), "restaurants",
                merchant="КОФЕ-ПОИНТ")
        for _ in range(rng.randint(1, 2)):
            name = rng.choice(("АЗС ЛУКОЙЛ", "ГАЗПРОМНЕФТЬ"))
            add(today - timedelta(days=DAYS - week * 7 - rng.randint(0, 6)),
                f"{name} АЗС", _rnd_amount(rng, 150000, 350000), "fuel", merchant=name)
    for month_shift in range(5):
        day = today - timedelta(days=30 * month_shift + 5)
        add(day, "ЖКХ", _rnd_amount(rng, 500000, 800000), "utilities")
        add(day, "АПТЕКА", _rnd_amount(rng, 30000, 150000), "health")
        add(day, "КИНО", _rnd_amount(rng, 60000, 120000), "entertainment")
        add(day, "ОДЕЖДА", _rnd_amount(rng, 100000, 400000), "clothing")
        add(day, "ПЕРЕВОД ДРУГУ", -100000, "transfers", merchant="ДРУГ")

    # --- гарантированные траты текущей недели (витрина окна дайджеста) ---
    add(today - timedelta(days=1), "ЛЕНТА", -285000, "groceries")
    add(today - timedelta(days=3), "ВКУСНО И ТОЧКА", -142000, "restaurants")
    add(today - timedelta(days=4), "КИНО", -90000, "entertainment")
    add(today - timedelta(days=2), "ЯНДЕКС ТАКСИ", -54000, "transport")

    # --- аномалии: крупная сумма + near-дубль ---
    add(today - timedelta(days=3), "ТЕХНОГИГАНТ", -8990000, "household")
    add(today - timedelta(days=2), "КОФЕ", -30000, "restaurants", merchant="КОФЕ")
    add(today - timedelta(days=2), "КОФЕ УГЛОВОЕ", -30000, "restaurants", merchant="КОФЕ")

    # --- правки/examples/cache → suggest-rules кандидаты ---
    for off in (40, 70, 100):
        add(today - timedelta(days=off), "МАГНИТ У ДОМА", -120000, "groceries",
            source="correction", merchant="МАГНИТ У ДОМА")
    store.add_example("МАГНИТ У ДОМА", -120000, "groceries")
    store.add_example("ЯНДЕКС GO", -35000, "transport")
    store.add_example("ПЕКАРНЯ ХЛЕБ", -80000, "restaurants")
    store.merchant_cache_set("МАГНИТ У ДОМА", "groceries")
    store.merchant_cache_set("ПЕКАРНЯ ХЛЕБ", "restaurants")

    # --- очередь на подтверждение ---
    pending = (
        ("СТРОЙКАОПТ МСК", "СТРОЙКАОПТ", -455000, "household"),
        ("КАФЕ МОЛОКО 2", "КАФЕ МОЛОКО", -62000, "restaurants"),
        ("ФОТОЛАБ", "ФОТОЛАБ", -89000, "other"),
        ("ХИМЧИСТКА ЛЮКС", "ХИМЧИСТКА", -45000, "other"),
        ("ДЕТСКИЙ МИР", "ДЕТСКИЙ МИР", -310000, "household"),
        ("РЕМОНТ ОБУВИ", "РЕМОНТ ОБУВИ", -70000, "other"),
    )
    for i, (desc, merchant, amount, llm_cat) in enumerate(pending[:PENDING_COUNT]):
        add(today - timedelta(days=10 - i), f"{desc} ОПЛАТА", amount, "other",
            source="llm_pending_review", merchant=merchant,
            category_llm=(None if i == 4 else llm_cat), review_status="pending",
            confidence=0.35 + i * 0.08)

    # --- бюджеты: считаем траты текущего месяца и ставим лимиты (1 перерасход, 1 ~80%) ---
    from spendtrack.reports import report_month

    month = today.strftime("%Y-%m")
    spent = {c["category"]: -c["total_k"] for c in report_month(store, month)["categories"]
             if c["total_k"] < 0}
    factors = {"groceries": 1.25, "restaurants": 1.6, "transport": 2.0,
               "entertainment": 0.7, "clothing": 1.4}
    budgets = []
    for cat, factor in factors.items():
        s = spent.get(cat, 0)
        amount = int(s * factor) if s > 0 else 300000  # в начале месяца — базовый лимит (0%)
        store.set_budget(cat, max(10000, amount))
        budgets.append(cat)

    fps = [r["fingerprint"] for r in store.conn.execute(
        "SELECT fingerprint FROM transactions WHERE import_batch=?", (batch,))]
    return {"batch": batch, "fingerprints": fps, "budgets": budgets,
            "examples": ["МАГНИТ У ДОМА", "ЯНДЕКС GO", "ПЕКАРНЯ ХЛЕБ"],
            "merchant_cache": ["МАГНИТ У ДОМА", "ПЕКАРНЯ ХЛЕБ"]}


def _open_store(db_path: Path):
    from spendtrack.store import Store

    return Store(db_path=db_path)


def feature_probe(store, today: date | None = None) -> dict:
    from spendtrack.digest import build_digest
    from spendtrack.recurring import detect_recurring
    from spendtrack.suggestions import suggest_rules

    subs = detect_recurring(store, today)
    anomaly_types = sorted({a["type"] for a in build_digest(store, today=today)["anomalies"]})
    return {
        "transactions": store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"],
        "recurring": len(subs),
        "active_subscriptions": sum(1 for s in subs if s["active"]),
        "anomaly_types": anomaly_types,
        "pending": store.pending_count(),
        "budgets": len(store.budget_map()),
        "suggest_candidates": len(suggest_rules(store)["candidates"]),
    }


VERIFY_MIN = {"recurring": 4, "pending": 6, "budgets": 5, "suggest_candidates": 1}


def _verify(store, today: date | None = None) -> bool:
    probe = feature_probe(store, today)
    print(json.dumps(probe, ensure_ascii=False, indent=1))
    missing = [k for k, v in VERIFY_MIN.items() if probe[k] < v]
    expected_anomalies = {"large_expense", "price_jump", "near_duplicate"}
    if not expected_anomalies.issubset(set(probe["anomaly_types"])):
        missing.append("anomaly_types")
    if missing:
        print(f"verify: НЕ ХВАТАЕТ: {', '.join(missing)} — профиль демо устарел, поправь генератор")
        return False
    print("verify: все витринные фичи на месте")
    return True


def cmd_seed(args) -> int:
    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    mpath = manifest_path(db)
    if db.name == "spend.db" and not args.force:
        print("seed: это похоже на реальную БД (spend.db). Демо сеется в data/demo.db;"
              " для осознанной записи в реальную БД — --force.")
        return 3
    nonempty = False
    if db.exists():
        store = _open_store(db)
        nonempty = store.conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] > 0
        store.close()
    if args.if_empty and nonempty:
        print(f"seed: БД не пуста ({db}) — пропуск (--if-empty)")
        return 0
    if nonempty and not args.force:
        print(f"seed: в {db} уже есть транзакции. Для демо используйте data/demo.db"
              f" или --force (осознанно), либо сначала clean.")
        return 3
    today = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    store = _open_store(db)
    try:
        manifest = build(store, today)
        manifest.update({"created": datetime.now(UTC).isoformat(timespec="seconds"),
                         "db": str(db)})
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"seed: {len(manifest['fingerprints'])} транзакций, бюджетов {len(manifest['budgets'])},"
              f" манифест {mpath}")
        ok = _verify(store, today)
    finally:
        store.close()
    return 0 if ok else 1


def cmd_status(args) -> int:
    db = Path(args.db)
    if not db.exists():
        print(f"status: нет БД {db}")
        return 1
    store = _open_store(db)
    try:
        print(json.dumps(feature_probe(store), ensure_ascii=False, indent=1))
    finally:
        store.close()
    print(f"manifest: {'есть' if manifest_path(db).exists() else 'нет'}")
    return 0


def cmd_clean(args) -> int:
    db = Path(args.db)
    mpath = manifest_path(db)
    if not mpath.exists():
        print(f"clean: нет манифеста {mpath} — нечего чистить (или демо не сеялось)")
        return 1
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    store = _open_store(db)
    try:
        fps = manifest.get("fingerprints", [])
        for i in range(0, len(fps), 500):
            chunk = fps[i:i + 500]
            marks = ",".join("?" * len(chunk))
            store.conn.execute(f"DELETE FROM transactions WHERE fingerprint IN ({marks})", chunk)
        if manifest.get("batch"):
            store.conn.execute("DELETE FROM import_batches WHERE id=?", (manifest["batch"],))
        for cat in manifest.get("budgets", []):
            store.conn.execute("DELETE FROM budgets WHERE category=?", (cat,))
        for desc in manifest.get("examples", []):
            store.conn.execute("DELETE FROM examples WHERE description=?", (desc,))
        for merchant in manifest.get("merchant_cache", []):
            store.conn.execute("DELETE FROM merchant_cache WHERE merchant=?", (merchant,))
        store.conn.commit()
    finally:
        store.close()
    mpath.unlink()
    print(f"clean: удалено транзакций {len(manifest.get('fingerprints', []))}, манифест снят")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="demo_data", description="Демо-данные Spendtrack")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("seed", cmd_seed), ("status", cmd_status), ("clean", cmd_clean)):
        p = sub.add_parser(name)
        p.add_argument("--db", default=str(DEFAULT_DB))
        p.set_defaults(fn=fn)
    sub.choices["seed"].add_argument("--if-empty", action="store_true")
    sub.choices["seed"].add_argument("--force", action="store_true")
    sub.choices["seed"].add_argument("--date", default=None, help="YYYY-MM-DD (для воспроизводимости)")
    sub.choices["seed"].add_argument("--verify", action="store_true", help="(по умолчанию verify уже включён)")
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
