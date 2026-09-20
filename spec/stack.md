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

## LLM-маршрут (резолв — `resolve_providers()` в llm.py)
1. BYO (`SPENDTRACK_LLM_BASE_URL/MODEL/API_KEY`) — свой OpenAI-совместимый сервер; единственный провайдер без фолбэков.
2. Ollama-пресет (`SPENDTRACK_LLM_PROVIDER=ollama`) — локально (air-gap), модель из `llm.offline`
   (`qwen2.5-coder:3b`; НЕ фолбэк free-цепочки, а отдельный режим «полностью на своей машине»).
3. free-цепочка (ключи; локальные шимы — дополнительно `SPENDTRACK_ALLOW_LOCAL_LLM=1`):
   OpenRouter :free (`nvidia/nemotron-3-super-120b-a12b:free`) → FreeLLMAPI `localhost:3001` →
   abacus-web shim `127.0.0.1:3201` (токен TTL 1ч; пауза до 20.09).
4. offline: правила/кэш — ядро работает без сети (LLM недоступен → rule-only).

## Тесты
- pytest, **317 unit + 18 e2e** (Playwright), все оффлайн (LLM через `classify_with_injectable`-стаб, сеть не ходит).
- ruff (lint) чистый.