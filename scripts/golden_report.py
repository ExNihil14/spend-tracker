"""Отчёт по golden-набору мерчантов (§G-4, не тест-гейт): доля rule-хитов, нерешённых, ошибок.

Запуск: `uv run python scripts/golden_report.py [--out reports/golden.json]`
Набор: `tests/golden/merchants.csv` (description, expected_category, bank).

Метрики: `rule_hit_share` (от строк с ожиданием) · `misclassified` (правило дало неверную категорию) ·
`unresolved` (правила не нашли — кандидат в LLM/очередь) · `surprise` (правило сработало там, где
ожидания нет). Это основа калибровки порога 0.9 на реальных фикстурах (K4): набор можно расширять,
не меняя код.
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.categorize import categorize_rules_only
from spendtrack.config import ROOT
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy

GOLDEN = ROOT / "tests" / "golden" / "merchants.csv"


def load_rows(path: Path = GOLDEN) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        raw = list(csv.DictReader(f))
    rows: list[dict] = []
    for r in raw:
        desc = (r.get("description") or "").strip()
        if not desc:
            continue
        rows.append({"description": desc,
                     "expected": (r.get("expected_category") or "").strip(),
                     "bank": (r.get("bank") or "").strip()})
    return rows


def compute(rows: list[dict], classify) -> dict:
    """classify(row) -> category|None. Чистая функция: считается без БД и легко тестируется."""
    results = [(r, classify(r)) for r in rows]
    known = [(r, got) for r, got in results if r["expected"]]
    unknown = [(r, got) for r, got in results if not r["expected"]]
    hit = [(r, got) for r, got in known if got == r["expected"]]
    mis = [(r, got) for r, got in known if got and got != r["expected"]]
    unresolved = [(r, got) for r, got in results if got is None]
    surprise = [(r, got) for r, got in unknown if got]
    n = len(rows)
    return {
        "rows": n,
        "known": len(known),
        "known_hit": len(hit),
        "rule_hit_share": round(len(hit) / len(known), 4) if known else 0.0,
        "misclassified": len(mis),
        "unresolved": len(unresolved),
        "unresolved_share": round(len(unresolved) / n, 4) if n else 0.0,
        "surprise": len(surprise),
        "details": {
            "missed": [f"{r['description']} (ожидали {r['expected']}, получили {got})"
                       for r, got in known if got != r["expected"]][:10],
            "unresolved": [r["description"] for r, _ in unresolved][:10],
            "surprise": [f"{r['description']} → {got}" for r, got in surprise][:10],
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Отчёт по golden-набору мерчантов (read-only)")
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "golden.json")
    ap.add_argument("--golden", type=Path, default=GOLDEN)
    args = ap.parse_args(argv)

    taxonomy = load_taxonomy()
    rows = load_rows(args.golden)
    with tempfile.TemporaryDirectory(prefix="golden-") as tmp:
        store = Store(db_path=Path(tmp) / "golden.db")
        try:
            def classify(row: dict) -> str | None:
                return categorize_rules_only(
                    {"description": row["description"], "merchant": row["description"]}, taxonomy, store)

            report = compute(rows, classify)
        finally:
            store.close()

    report["generated"] = datetime.now(UTC).isoformat(timespec="seconds")
    report["golden_file"] = str(args.golden)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"golden: {report['known_hit']}/{report['known']} rule-хитов "
          f"({report['rule_hit_share'] * 100:.0f}%), нерешённых {report['unresolved']}/{report['rows']}, "
          f"ошибок {report['misclassified']}, сюрпризов {report['surprise']}")
    print(f"отчёт: {args.out}")
    return 0  # отчёт, не гейт: решение о порогах — за автором (K4)


if __name__ == "__main__":
    raise SystemExit(main())
