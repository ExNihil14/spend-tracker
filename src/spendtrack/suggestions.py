"""Подсказки keyword-правил из решений пользователя (read-only, без LLM и записей).

Источники «человеческого решения»:
- явные правки: `transactions.category_source='correction'`;
- переопределения LLM: решённые строки (`review_status='approved'`) с `category != category_llm`
  (pending/skipped — не решение и не учитываются);
- few-shot `examples(description, category)`.

Кандидаты: униграммы и биграммы из нормализованных описаний (UPPER, без цифр/дат/коротких токенов)
плюс отдельный тип «merchant» (полное имя мерчанта). Кандидат проходит при подтверждениях >= N
и чистоте (доля доминирующей категории) >= P; конфликты категорий показываются, а не скрываются.
Статус относительно taxonomy.toml считается через `taxonomy_repo.analyze_rules`
(новое / дубль / будет мёртвым / пересечение). Ничего не записывается — только предложения.
"""
from __future__ import annotations

import re
from collections import Counter
from itertools import pairwise

from spendtrack import taxonomy_repo
from spendtrack.store import Store

MIN_CONFIRMATIONS = 3
MIN_PURITY = 0.8
MIN_TOKEN_LEN = 3
PATTERN_MAX_LEN = 64  # ограничение taxonomy.validate_pattern
STOPWORDS = {"ООО", "ИП", "ЗАО", "ОАО", "ПАО", "LLC", "LTD", "INC"}

DECIDED_TX_SQL = (
    "SELECT description, merchant, category FROM transactions"
    " WHERE category_source = 'correction'"
    "    OR (review_status = 'approved' AND category_llm IS NOT NULL AND category_llm != ''"
    "        AND category != category_llm)"
)

_NORM = re.compile(r"[^А-ЯЁA-ZІЇҐЎ]+")  # расширенная кириллица (UA/BY) не рвёт токены


def _tokens(description: str) -> list[str]:
    return [t for t in _NORM.split((description or "").upper())
            if len(t) >= MIN_TOKEN_LEN and t not in STOPWORDS]


def _finalize(pattern: str, kind: str, cats: Counter, examples: list[str],
              min_confirmations: int, min_purity: float) -> dict | None:
    if not 2 <= len(pattern) <= PATTERN_MAX_LEN:  # контракт taxonomy.validate_pattern (2-64)
        return None
    total = sum(cats.values())
    if total < min_confirmations:
        return None
    category, best = cats.most_common(1)[0]
    purity = best / total
    if purity < min_purity:
        return None
    return {
        "pattern": pattern,
        "type": kind,
        "category": category,
        "confirmations": total,
        "purity": round(purity, 3),
        "conflicts": {c: n for c, n in cats.items() if c != category},
        "examples": examples,
    }


def _decided_rows(store: Store) -> list[dict]:
    rows = [dict(r) for r in store.conn.execute(DECIDED_TX_SQL).fetchall()]
    rows += [dict(r) for r in store.conn.execute("SELECT description, category FROM examples")]
    return rows


def _ngram_candidates(rows: list[dict], min_confirmations: int, min_purity: float) -> list[dict]:
    stats: dict[str, dict] = {}
    for row in rows:
        tokens = _tokens(row["description"])
        for pattern in set(tokens) | {f"{a} {b}" for a, b in pairwise(tokens)}:
            bucket = stats.setdefault(pattern, {"cats": Counter(), "examples": []})
            bucket["cats"][row["category"]] += 1
            if row["description"] and len(bucket["examples"]) < 3 and row["description"] not in bucket["examples"]:
                bucket["examples"].append(row["description"])
    out = []
    for pattern, bucket in stats.items():
        candidate = _finalize(pattern, "ngram", bucket["cats"], bucket["examples"],
                              min_confirmations, min_purity)
        if candidate:
            out.append(candidate)
    return out


def _merchant_candidates(store: Store, min_confirmations: int, min_purity: float) -> list[dict]:
    rows = store.conn.execute(
        "SELECT merchant, category, COUNT(*) AS n FROM transactions"
        " WHERE merchant IS NOT NULL AND merchant != ''"
        "   AND (category_source = 'correction'"
        "        OR (review_status = 'approved' AND category_llm IS NOT NULL AND category_llm != ''"
        "            AND category != category_llm))"
        " GROUP BY merchant, category").fetchall()
    by_merchant: dict[str, Counter] = {}
    for row in rows:
        by_merchant.setdefault(row["merchant"], Counter())[row["category"]] = row["n"]
    out = []
    for merchant, cats in by_merchant.items():
        candidate = _finalize(merchant, "merchant", cats, [], min_confirmations, min_purity)
        if candidate:
            out.append(candidate)
    return out


def _rule_status(pattern: str, analysis: list[dict]) -> tuple[str, str]:
    p = pattern.upper()
    for a in analysis:
        if not a["invalid_category"] and a["pattern"].upper() == p:  # битые не срабатывают в рантайме
            return "дубль", f"уже есть #{a['index']} «{a['pattern']}» → {a['category']}"
    for a in analysis:
        if not a["invalid_category"] and a["pattern"].upper() in p:
            return "будет мёртвым", f"перехватит #{a['index']} «{a['pattern']}»"
    for a in analysis:
        ap = a["pattern"].upper()
        if not a["invalid_category"] and ap != p and p in ap:
            # существующее правило длиннее → оно уже/конкретнее, кандидат шире по охвату
            return "пересечение", f"пересекается с #{a['index']} «{a['pattern']}» (существующее правило уже)"
    return "новое", ""


def suggest_rules(store: Store, min_confirmations: int = MIN_CONFIRMATIONS,
                  min_purity: float = MIN_PURITY) -> dict:
    rows = _decided_rows(store)
    merchant = _merchant_candidates(store, min_confirmations, min_purity)
    merchant_patterns = {c["pattern"] for c in merchant}
    ngram = [c for c in _ngram_candidates(rows, min_confirmations, min_purity)
             if c["pattern"] not in merchant_patterns]
    analysis = taxonomy_repo.analyze_rules()
    candidates = merchant + ngram
    for candidate in candidates:
        candidate["status"], candidate["status_detail"] = _rule_status(candidate["pattern"], analysis)
    candidates.sort(key=lambda c: (-c["confirmations"], -c["purity"], c["pattern"]))
    return {
        "decided_rows": len(rows),
        "min_confirmations": min_confirmations,
        "min_purity": min_purity,
        "candidates": candidates,
    }
