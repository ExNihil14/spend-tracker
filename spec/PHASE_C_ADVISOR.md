# Phase C — LLM advisor (fact-sheet + slots): design spec v2

Status: **design v2** — 27.10.2026. Owner defaults approved: CLI; templates by default; category names
may leave the machine; merchant names/descriptions must not; LLM sees aggregates only.
v2 incorporates the Opus design review (FIX-FIRST: 3 P1, 9 P2, P3 notes). No live/LLM calls in design.

## 1. Goal and scope

Answer owner questions about spending, offline-first:

- total for a period; category sums (calendar months);
- budget overruns (calendar months);
- daily trend (total per day) for the last N days or a month;
- top-N categories (N parsed, default 3).

Out of scope: writing transactions; RAG/embeddings; pandas; new dependencies; raw-row LLM prompts;
per-category daily series (daily facts have no category dimension — explicitly not offered).

## 2. Privacy invariant (hard)

### 2.1 Fact-sheet schema (exact allow-list)

```
period: {start:"YYYY-MM-DD", end:"YYYY-MM-DD", label: <one of generated labels>, month: "YYYY-MM"|null}
base_currency: "RUB"
total: int            # kopecks, RUB only
tx_count: int         # RUB-only rows
categories: [{name: <taxonomy name>, sum: int, count: int, share_bp: int}] | null
budgets: [{category: <taxonomy>, limit: int, spent: int, overrun: int}] | null
daily: [{date:"YYYY-MM-DD", sum: int}]
excluded_foreign: {count: int, currencies: [str]}   # codes only, no amounts
compare: {total: int, daily: [...], label: str} | null
unavailable: [str]    # e.g. ["categories","budgets"] for non-month periods
```

No other keys at any level. `share_bp` is an integer in basis points (10000 = 100%).
`validate_facts(facts)` enforces: exact key set, `int` amounts, ISO dates, `name`/`category` in
`taxonomy_names ∪ {UNCATEGORIZED}`, `period.label` from the generated set. It runs in `build_facts`
and immediately before every LLM call; a violation raises and the caller falls back to templates.

### 2.2 Sentinel test

Seed a store whose `description`, `merchant`, `account` fields contain unique sentinels
(`SENTINEL_MERCHANT_7f3a`, `SENTINEL_ACCOUNT_91c2`, …). Assert no sentinel appears in: serialized facts,
`--json` output, and every prompt captured by the stub LLM (slot fallback included).

### 2.3 User question redaction

Merchant names can appear in the question. Before any LLM call:
- drop digit runs longer than 3 characters;
- drop tokens matching a known merchant/description string from local tables (never sent);
- if anything was dropped or a merchant token was found → do not call the LLM; answer with the
  deterministic template: "по магазинам не отвечаю — только по категориям и периодам".
The slot-fallback prompt contains the sanitized question plus the category-name list only.

## 3. Interfaces

### 3.1 Period and report ranges

```python
@dataclass(frozen=True)
class Period:
    start: str; end: str; label: str; month: str | None
```

- Calendar months use `reports.py` directly.
- N-day ranges: `build_facts` calls `report_daily` for each month the range touches and **slices by
  date inside the advisor** for `total` and `daily[]`; `categories`/`budgets` are `null` and
  `unavailable` lists them. No changes to `reports.py`; no new date math beyond date comparison.
- `parse_period(text, today: date)` is injectable (tests pass `today`; CLI uses `date.today()`).
- Ambiguity rules: a bare month name resolves to the most recent such month **≤ today's month**;
  N-day bounds are 1..365, otherwise `unknown` + ask-back (no silent clamp); accepted forms: genitive
  and prepositional RU forms for all 12 months, `YYYY-MM`, `последние N дней`, `этот/прошлый месяц`.
- `--month YYYY-MM` overrides the question period and the answer echoes the override in `label`;
  invalid `--month` → exit 2.

### 3.2 Slots

```python
@dataclass(frozen=True)
class Slots:
    period: Period
    metric: str          # total|category|budget|trend|top|unknown
    category: str | None # canonical taxonomy name
    top_n: int           # default 3, parsed 1..10
    compare: bool
    ask_back: str | None # reason: ambiguous/unknown period/category
```

Deterministic regex first. LLM slot fallback (optional, sanitized question + category list) may return
only `metric`/`category`/`top_n`; values are validated against the enum and taxonomy, else `unknown`.
The LLM **never** produces a `Period`. Ambiguous alias → ask-back listing candidates; unresolved
category or unknown period → `unknown` → ask-back. A valid category with no spend answers "0 ₽".

### 3.3 Fact building

`build_facts(store, period)` composes `report_month`, `categories_with_totals`, `budgets_progress`,
`report_daily` (calendar month) or slices daily rows (N-day). `tx_count` counts RUB rows only;
`excluded_foreign` records excluded rows by currency code. Empty month → zero totals, empty lists,
no exception. `base_currency="RUB"` (fixed; foreign excluded).

### 3.4 Answer routing (explicit)

| slots | LLM | action |
|---|---|---|
| known intent, unambiguous | off/on | template (LLM not called) |
| `unknown`, redaction hit | any | "по магазинам не отвечаю…" |
| `unknown`, no redaction, LLM off | off | ask-back template |
| `unknown`, no redaction, LLM on | on | free-form: validated fact-sheet + sanitized question; on error/timeout/invalid → ask-back |
| known but question asks "почему/что делать" | on | free-form (facts only), template fallback |

Templates (RU, `fmt_amount`, `plural_ru`):
- total: "За <label> — <sum> (<n> операций)." + compare line if requested;
- category: "<Category>: <sum> (<share>%), <n> операций.";
- budget: "Перерасход: …" or "В рамках бюджетов." + pace (spent/limit vs elapsed/days);
- trend: "Средний день <sum>; максимум <date> — <sum>; к прошлому периоду <±x%>.";
- top: "Топ-<N>: …"; fewer categories → list all.
Zero-division rules: previous total 0 → "нет данных за прошлый период"; total 0 → share "—".
Average day divisor = elapsed days for the current month, otherwise calendar days in the period.
Partial current month compare uses the same day-range of the previous month and says so.

### 3.5 Answer validation

Every number in an LLM answer must match a formatted value from the facts (`fmt_amount`, share_bp,
date, count). Otherwise discard and use the template. `facts_used` is informational only.

### 3.6 CLI

```
spendtrack ask "..." [--month YYYY-MM] [--json] [--no-llm]
```

Exit codes: 0 answer (including template fallback on LLM failure), 2 empty question / invalid
`--month` / conflicting `--month` (override is allowed and echoed; only malformed input is 2),
3 unknown + ask-back. `--json` returns `{intent, period, answer, facts}` with the validated sheet and
pinned schema (including `null`/`unavailable`). With LLM off and no `--no-llm`, a spy asserts zero
LLM calls.

## 4. Milestones (TDD)

| # | deliverable | tests |
|---|-------------|-------|
| C1 | `Period`, `parse_period(today)`, `build_facts`, `validate_facts` | empty/foreign-only month, N-day across month boundary, extra key rejected, non-taxonomy name rejected, compare |
| C2 | `slots.py` regex + LLM fallback validation | injected today + Jan rollover, all 12 months genitive/prepositional, N bounds 1/365, alias uniqueness over taxonomy.toml, ambiguous alias, garbage LLM JSON |
| C3 | templates (`answer.py`) | 6 intents, zero-division, partial-month compare, plurals 1/2/5/11/21/22, kopeck formatting, top-N |
| C4 | LLM free-form + redaction + post-check | sentinel scan of every prompt, redacted question, invented-number rejection, LLM-off spy, timeout fallback |
| C5 | CLI `ask`/`--json` | `--month` override/conflict, exit codes 0/2/3, JSON schema snapshot, corrupt DB |

Definition of done: offline tests green; ruff; no core signature changes; privacy + sentinel tests;
one external design review (Opus) — done, findings incorporated in v2.

## 5. Risks

- Alias drift → alias-uniqueness test over `taxonomy.toml`.
- Month boundaries/timezone → reuse `reports.py`; injectable `today`.
- Multi-currency → RUB-only totals + `excluded_foreign`, templates mention exclusions.
- LLM hallucination → templates first, number post-check, facts allow-list.
- Prompt leak → structural validation, redaction, sentinel tests.

## 6. Resolved decisions

- CLI first (UI later); templates by default; free-form optional; categories allowed, merchants not.
- N-day trend = total-per-day only (no per-category series).
- `--month` overrides and is echoed; ambiguous/invalid periods ask back.
