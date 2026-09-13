# SPEC: Стек Spendtrack (зафиксировано 13.09.2026)

Фиксация зафиксированного стека и версий (Фаза 1 MASTER_PLAN.md). Менять только через spec/review.

## Языки/рантайм
- Python 3.13.15 (uv-managed), сборка: `uv run pytest`, `uv run ruff check`.
- Без pandas/embeddings в этом проекте (RAG — отдельная вилка).

## Backend
- FastAPI + uvicorn, порт 8766 (`uv run uvicorn spendtrack.main:app --port 8766`, или run.ps1).
- Pydantic v2 (settings через pydantic-settings), SQLite через стандартный `sqlite3` (WAL).
- Суммы = `amount_kopecks INTEGER` (копейки), НЕ REAL/DECIMAL.

## Frontend
- htmx + Jinja2 server-rendered шаблоны (templates/{base,index,approve}.html).
- Tailwind CSS v4 vendored: `static/tailwind.js` (282KB, без npm-сборки).
- НЕ React (решение stack-анализа 13.09.2026 — см. continue.md «Stack-вердикт»).

## Данные
- SQLite (WAL) — единственная БД. Правило SQLite-first: PostgreSQL/Redis не добавлять
  без измеренной необходимости (конкурентные юзеры >10, JSONB/CTE-потребности).
- fingerprint-дедуп sha1(date|amount|desc|account_anon|export_rowid) — повторный импорт no-op.

## LLM-маршрут (порядок попыток в llm.py)
1. primary: FreeLLMAPI `http://localhost:3001/v1` → glm-4.5-flash.
2. fallback: OpenRouter :free → `nvidia/nemotron-3-super-120b-a12b:free`.
3. deepseek: abacus-web shim `http://127.0.0.1:3201/v1` → `deepseek-v4-1-flash`
   (0 кредитов, 1M ctx; токен TTL 1ч — обновлять session.json из curl браузера).
4. offline: Ollama → qwen2.5-coder:3b (не для категоризации — только текстовая классификация без учёта JSON-контракта; правила работают и без LLM).

## Тесты
- pytest, 37 passed, все оффлайн (LLM через `classify_with_injectable`-стаб, сеть не ходит).
- ruff (lint) чистый.