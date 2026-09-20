from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.categorize import categorize_transaction
from spendtrack.reports import confidence_calibration, report_month
from spendtrack.store import Store, fmt_amount, parse_amount
from spendtrack.taxonomy import load_taxonomy


def make_store() -> Store:
    return Store()


def cmd_add(args) -> int:
    store = make_store()
    taxonomy = load_taxonomy()
    amount = parse_amount(args.amount)
    category = args.category or categorize_transaction(
        {"date": args.date, "description": args.description, "amount_kopecks": amount,
         "merchant": args.description.upper()[:20], "account_anon": None},
        taxonomy, store,
    )["category"]
    tx_id = store.add_transaction(
        date=args.date, description=args.description, amount_kopecks=amount,
        category=category, category_source="manual" if args.category else "llm",
        merchant=args.description.upper()[:20],
    )
    if tx_id:
        print(f"OK id={tx_id} {fmt_amount(amount)} {args.description} -> {category}")
        return 0
    print("dup (уже есть)")
    return 1


def cmd_import(args) -> int:
    store = make_store()
    raw = Path(args.file).read_text(encoding="utf-8-sig", errors="replace")
    from spendtrack.csv_import import ImportLimitError, import_csv
    try:
        result = import_csv(raw, store, bank=args.bank)
    except ImportLimitError as e:  # лимиты импорта — понятный код 1
        print(f"ошибка импорта: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_report(args) -> int:
    store = make_store()
    month = args.month
    if not month:
        row = store.conn.execute("SELECT MAX(date) m FROM transactions").fetchone()
        month = (row["m"] or "")[:7]
    report = report_month(store, month)
    print(f"== {month} | income {fmt_amount(report['income_k'])} | "
          f"expense {fmt_amount(report['expense_k'])} | balance {fmt_amount(report['balance_k'])}")
    for c in report["categories"]:
        print(f"  {c['category']:<18} {fmt_amount(c['total_k']):>12}  n={c['count']}")
    return 0


def cmd_count(args) -> int:
    store = make_store()
    counts = store.counts()
    print(json.dumps(counts, ensure_ascii=False))
    return 0


def cmd_confidence(args) -> int:
    from spendtrack.config import load_settings
    store = make_store()
    current = load_settings().acceptance.auto_accept_confidence
    rep = confidence_calibration(store, current_threshold=current)
    print(f"Калибровка порога авто-приёма: всего с предложением LLM {rep['total']}, "
          f"решено {rep['resolved']}, в очереди {rep['pending']}, пропущено {rep['skipped']}")
    if rep["low_data"] and rep["resolved"]:
        print(f"  данных мало (решено {rep['resolved']} < 20) — оценка ориентировочная")
    if rep["buckets"]:
        print(f"  {'conf':>5}  {'решено':>6}  {'совпало':>7}  {'исправлено':>10}  {'ошибок':>7}")
        for b in rep["buckets"]:
            print(f"  {b['bucket']:>5}  {b['n']:>6}  {b['agreed']:>7}  {b['corrected']:>10}"
                  f"  {b['wrong_rate'] * 100:>6.1f}%")
    else:
        print("  нет данных: решённых LLM-предложений в БД пока нет")
    if rep["resolved"]:
        print("  если авто-принимать с conf >= t:")
        for t in rep["thresholds"]:
            print(f"    t={t['threshold']:.1f}: принято {t['accepted']} ({t['coverage'] * 100:.0f}%), "
                  f"ошибочных {t['corrected']} ({t['wrong_rate'] * 100:.1f}%)")
    print(f"Текущий порог (config/settings.toml): {rep['current_threshold']}")
    return 0


def cmd_budget(args) -> int:
    from spendtrack.reports import budgets_progress
    from spendtrack.taxonomy import load_taxonomy
    store = make_store()
    month = args.month
    if not month:
        row = store.conn.execute("SELECT MAX(date) m FROM transactions").fetchone()
        month = (row["m"] or datetime.now(UTC).strftime("%Y-%m-%d"))[:7]
    items = budgets_progress(store, month, known={c.name for c in load_taxonomy().categories})
    print(f"== Бюджеты {month}")
    if not items:
        print("  бюджеты не заданы (настроить: /settings)")
        return 0
    for b in items:
        mark = "  ПЕРЕРАСХОД" if b["over"] else ""
        print(f"  {b['category']:<18} {fmt_amount(b['spent_k']):>12} / {fmt_amount(b['budget_k']):>12}"
              f"  {b['pct']:>4.0f}%{mark}")
    return 0


def cmd_recurring(args) -> int:
    from spendtrack.recurring import recurring_summary
    store = make_store()
    summary = recurring_summary(store)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    items = summary["subscriptions"]
    print(f"== Рекурринги/подписки: найдено {len(items)}, активных {summary['active_count']}, "
          f"месячный итог {fmt_amount(-summary['monthly_total_k'])}")
    for s in items:
        status = "активна" if s["active"] else f"нет списаний {s['days_since_last']} дн"
        skipped = f", пропуск {s['skipped_months']}" if s["skipped_months"] else ""
        print(f"  {s['merchant']:<20} {fmt_amount(-s['price_k']):>10} / мес  n={s['occurrences']}"
              f"  {s['first_date']}→{s['last_date']}  ~{s['median_gap_days']} дн{skipped}  [{status}]")
    return 0


def cmd_suggest_rules(args) -> int:
    from spendtrack.suggestions import suggest_rules
    store = make_store()
    report = suggest_rules(store)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    items = report["candidates"]
    print(f"== Предложения правил: решённых строк {report['decided_rows']}, кандидатов {len(items)}"
          f" (пороги: n>={report['min_confirmations']}, чистота>={report['min_purity']:.0%})")
    for c in items:
        conflict = ""
        if c["purity"] < 1.0:
            others = ", ".join(f"{cat} {n}" for cat, n in c["conflicts"].items())
            conflict = f"  конфликт: {others}"
        detail = f" — {c['status_detail']}" if c["status_detail"] else ""
        print(f"  {c['pattern']:<28} {c['type']:<8} {c['category']:<14} n={c['confirmations']:<3}"
              f" {c['purity'] * 100:>3.0f}%  {c['status']}{detail}{conflict}")
    if not items:
        print("  предложений нет: правок мало или всё покрыто правилами (read-only, ничего не меняем)")
    return 0


def cmd_digest(args) -> int:
    from spendtrack.digest import DEFAULT_DAYS, build_digest
    store = make_store()
    days = args.days if args.days is not None else DEFAULT_DAYS
    digest = build_digest(store, days=days)
    if args.json:
        print(json.dumps(digest, ensure_ascii=False, indent=2))
        return 0
    p = digest["period"]
    print(f"== Дайджест {p['from']} → {p['to']} ({p['days']} дн)")
    print(f"  Доход   {fmt_amount(digest['income_k']):>12}  (было {fmt_amount(digest['prev']['income_k'])})")
    print(f"  Расход  {fmt_amount(digest['expense_k']):>12}  (Δ {fmt_amount(digest['expense_delta_k'])})")
    print(f"  Баланс  {fmt_amount(digest['balance_k']):>12}")
    print(f"  Средний расход/день: {fmt_amount(digest['avg_per_day_k'])}")
    if digest["top_day"]:
        d = digest["top_day"]
        print(f"  Самый дорогой день: {d['date']} ({fmt_amount(d['total_k'])})")
    for c in digest["top_categories"]:
        print(f"    {c['category']:<16} {fmt_amount(c['total_k']):>12}"
              f"  Δ {fmt_amount(c['delta_k']):>10}  n={c['count']}")
    print(f"  Очередь на подтверждение: {digest['pending_count']}")
    for u in digest["upcoming"]:
        when = (f"через {u['days_until']} дн" if u["days_until"] >= 0
                else f"просрочено на {-u['days_until']} дн")
        print(f"  Ожидается: {u['merchant']:<20} {fmt_amount(-u['price_k']):>10} ₽"
              f"  {u['next_expected']} ({when})")
    print(f"  Аномалии: {len(digest['anomalies'])}")
    for a in digest["anomalies"]:
        print(f"    [{a['label']}] {a['date']} {a['merchant']}: {a['detail']}")
    return 0


def cmd_llm_status(args) -> int:
    from spendtrack.llm import llm_status
    status = llm_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    titles = {
        "off": "выключен",
        "byo": "свой сервер (BYO)",
        "ollama": "локальный Ollama — данные не покидают машину",
        "free": "бесплатные каналы (free) — чужие серверы",
    }
    print(f"== LLM: {titles.get(status['mode'], status['mode'])}")
    if not status["providers"]:
        print("   данные не покидают машину, спорные строки → очередь")
        return 0
    for p in status["providers"]:
        key = "установлен" if p["has_key"] else "не нужен"
        print(f"   {p['source']:<9} {p['base_url']}  model={p['model']}  ключ: {key}")
    if status["mode"] == "free":
        print("   полный контроль над данными: BYO-ключ или Ollama (см. README/PRIVACY.md)")
    return 0


def cmd_doctor(args) -> int:
    from spendtrack.doctor import run_checks
    report = run_checks()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"doctor: {report['status'].upper()}")
        for c in report["checks"]:
            count = str(c["count"]) if c["count"] else "-"
            print(f"  {c['severity'].upper():<8} {c['id']:<20} {count:>5}  {c['detail']}")
    return 1 if report["status"] == "critical" else 0


def cmd_confirm(args) -> int:
    store = make_store()
    ok = store.update_category(args.id, args.category, source="correction")
    store.seed_merchant_cache(args.id)
    print("confirmed" if ok else "not found")
    return 0 if ok else 1


def _utf8_stdout() -> None:
    """Пайп/Git Bash на RU-Windows даёт cp1251: кириллица мазалась, а «≠» ронял печать.

    Реальная консоль Windows уже UTF-8 (PEP 528) — там no-op; pytest-capture тоже UTF-8.
    """
    out = sys.stdout
    enc = (getattr(out, "encoding", "") or "").lower()
    if enc not in ("utf-8", "utf8") and hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    p = argparse.ArgumentParser(prog="spendtrack", description="Трекер расходов")
    sub = p.add_subparsers(dest="cmd")

    a_add = sub.add_parser("add", help="-23.45 'milk'")
    a_add.add_argument("amount")
    a_add.add_argument("description")
    a_add.add_argument("--date", default="2026-09-12")
    a_add.add_argument("--category")
    a_add.set_defaults(fn=cmd_add)

    a_im = sub.add_parser("import")
    a_im.add_argument("file")
    a_im.add_argument("--bank", default="auto", choices=["auto", "sber", "tinkoff", "yandex"])
    a_im.set_defaults(fn=cmd_import)

    a_rp = sub.add_parser("report")
    a_rp.add_argument("--month", default=None)
    a_rp.set_defaults(fn=cmd_report)

    a_ct = sub.add_parser("count")
    a_ct.set_defaults(fn=cmd_count)

    a_cf = sub.add_parser("confirm")
    a_cf.add_argument("id", type=int)
    a_cf.add_argument("category")
    a_cf.set_defaults(fn=cmd_confirm)

    a_conf = sub.add_parser("confidence", help="калибровка порога авто-приёма LLM")
    a_conf.set_defaults(fn=cmd_confidence)

    a_bg = sub.add_parser("budget", help="прогресс по бюджетам категорий")
    a_bg.add_argument("--month", default=None)
    a_bg.set_defaults(fn=cmd_budget)

    a_doc = sub.add_parser("doctor", help="проверка целостности данных")
    a_doc.add_argument("--json", action="store_true", help="машинный вывод (JSON)")
    a_doc.set_defaults(fn=cmd_doctor)

    a_rec = sub.add_parser("recurring", help="детекция рекуррингов/подписок")
    a_rec.add_argument("--json", action="store_true", help="машинный вывод (JSON)")
    a_rec.set_defaults(fn=cmd_recurring)

    a_sr = sub.add_parser("suggest-rules", help="подсказки keyword-правил из правок (read-only)")
    a_sr.add_argument("--json", action="store_true", help="машинный вывод (JSON)")
    a_sr.set_defaults(fn=cmd_suggest_rules)

    a_dg = sub.add_parser("digest", help="дайджест недели + флаги аномалий (read-only)")
    a_dg.add_argument("--days", type=int, default=None, help="размер окна в днях (по умолчанию 7)")
    a_dg.add_argument("--json", action="store_true", help="машинный вывод (JSON)")
    a_dg.set_defaults(fn=cmd_digest)

    a_llm = sub.add_parser("llm-status", help="режим LLM: off/byo/ollama/free (без сети и ключей)")
    a_llm.add_argument("--json", action="store_true", help="машинный вывод (JSON)")
    a_llm.set_defaults(fn=cmd_llm_status)

    args = p.parse_args(argv)
    if args.cmd and hasattr(args, "fn"):
        return int(args.fn(args)) or 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())