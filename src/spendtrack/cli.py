from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spendtrack.categorize import categorize_transaction
from spendtrack.reports import report_month
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
    from spendtrack.csv_import import import_csv
    result = import_csv(raw, store, bank=args.bank)
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


def cmd_confirm(args) -> int:
    store = make_store()
    ok = store.update_category(args.id, args.category, source="correction")
    store.seed_merchant_cache(args.id)
    print("confirmed" if ok else "not found")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
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

    args = p.parse_args(argv)
    if args.cmd and hasattr(args, "fn"):
        return int(args.fn(args)) or 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())