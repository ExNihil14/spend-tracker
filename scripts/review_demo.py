"""Демо-данные для визуального smoke очереди /approve.

Использование:
    uv run python scripts/review_demo.py seed    # добавить демо-pending
    uv run python scripts/review_demo.py clean   # удалить демо-строки и их merchant_cache
    uv run python scripts/review_demo.py list    # показать текущую очередь

Помечает строки import_batch='DEMO_REVIEW', поэтому очистка безопасна и не
затрагивает реальные данные. Мерчантам даётся префикс «ДЕМО », чтобы убрать
merchant_cache, засеянный approve-действием (few-shot).
"""
from __future__ import annotations

import sys

from spendtrack.store import Store

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARK = "DEMO_REVIEW"
MERCHANT_PREFIX = "ДЕМО "

# (date, description, amount_kopecks, category, category_llm, confidence)
DEMO_ROWS = [
    # date ASC проверяет сортировку очереди (date ASC, amount DESC, id ASC)
    ("2026-09-05", "СТРОЙКАОПТ МСК (возможно стройматериалы)", -452_000, "other", "household", 0.55),
    ("2026-09-06", "КОФЕЙНЯ НА ЛЕНИНА", -38_000, "other", "restaurants", 0.62),
    ("2026-09-07", "АЗС №17 ТРАССА М7", -320_000, "other", "fuel", 0.50),
    ("2026-09-08", "МЕТРО ТЦ ГАЛЕРЕЯ", -150_000, "other", "transport", 0.71),
    ("2026-09-09", "ПЕРЕВОД ДРУГУ ИВАН", -500_000, "transfers", "transfers", 0.65),  # diff нет
    ("2026-09-10", "ВОЗВРАТ OZON", 129_000, "income", "transfers", 0.60),  # положительная сумма
    # одна дата: проверяем amount DESC. Вставляем «5 000» ПЕРЕД «1 000»;
    # числовой DESC ставит −1000 выше −5000 (т.е. «1 000 ₽» окажется выше).
    ("2026-09-11", "ДЕМО ПОКУПКА (5 000 руб)", -500_000, "other", "household", 0.58),
    ("2026-09-11", "ДЕМО ПОКУПКА (1 000 руб)", -100_000, "other", "groceries", 0.52),
]


def seed() -> None:
    store = Store()
    ids = []
    for date, desc, amount, cat, llm_cat, conf in DEMO_ROWS:
        tid = store.add_transaction(
            date=date, description=desc, amount_kopecks=amount,
            category=cat, category_source="llm_pending_review", confidence=conf,
            merchant=MERCHANT_PREFIX + desc.split()[0],
            import_batch=MARK, category_llm=llm_cat, review_status="pending",
        )
        if tid:
            ids.append(tid)
    print(f"seeded {len(ids)} pending rows (ids={ids}); pending_count={store.pending_count()}")
    store.close()


def clean() -> None:
    store = Store()
    n = store.conn.execute("DELETE FROM transactions WHERE import_batch=?", (MARK,)).rowcount
    m = store.conn.execute("DELETE FROM merchant_cache WHERE merchant LIKE ?",
                           (MERCHANT_PREFIX + "%",)).rowcount
    store.conn.commit()
    print(f"removed transactions={n}, merchant_cache={m}; pending_count={store.pending_count()}")
    store.close()


def lst() -> None:
    store = Store()
    rows = store.queued_for_review()
    print(f"pending_count={store.pending_count()}")
    for r in rows:
        print(f"  id={r['id']} {r['date']} {r['description'][:40]!r:44} "
              f"{r['amount_kopecks']:>10} cat={r['category']} llm={r['category_llm']} conf={r['confidence']}")
    store.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    {"seed": seed, "clean": clean, "list": lst}[cmd]()
