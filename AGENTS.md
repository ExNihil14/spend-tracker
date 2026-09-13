# Spendtrack — AGENTS.md

## Что это
Трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx, offline-first детерминированное ядро, LLM-шов только для остатка (~30-40% транзакций).

## Обязательные файлы в начале сессии
- `continue.md` — состояние проекта и следующие шаги (источник для продолжения работы).
- `spec/ARCHITECTURE.md` — архитектура/решения/план (источник истины).
- `CONTEXT.md` — словарь терминов (не перифразировать).
- Мастер-план из `D:\dev\docs\vibecoding\out_analysis\MASTER_PLAN.md` — практики/грабли/промпты (читай spec-раздел при изменениях).

## Команды
- Тест: `uv run pytest`
- Линт: `uv run ruff check src tests`
- Запуск: `uv run uvicorn spendtrack.main:app --port 8766` (или `.\run.ps1`)
- CLI: `uv run python -m spendtrack.cli add -23.45 "milk"` / `report` / `import file.csv --bank auto` / `count`
- Верификация (правило из MASTER_PLAN.md): после изменений проверять факт (diff/запуск/UI в браузере), а не только отчёт

## Layout
- `config/settings.toml` — порт, LLM-эндпоинты (primary/fallback/offline), авто-приём confidence (0.9)
- `config/taxonomy.toml` — 18 категорий + keyword-правила (править БЕЗ кода)
- `src/spendtrack/` — `store.py` (SQLite, копейки INTEGER), `categorize.py` (rule→llm→validation→queue), `csv_import.py` (BANKS-адаптеры), `reports.py`, `llm.py`+`prompts.py`, `routers/`, `cli.py`
- `data/spend.db` — автосоздаётся (WAL)
- `tests/` — все оффлайн, LLM стабится (injectable classify/llm_getter), не трогать контракты тестов без причины

## Ключевые решения (не менять без ревью)
- Суммы = `amount_kopecks INTEGER` (копейки), НЕ REAL
- Fingerprint-дедуп `sha1(date|amount|desc|account_anon|export_rowid)` — повторный импорт = no-op
- account псевдонимизируется (`account_pseudonyms`), сырые номера карт не хранятся
- Авто-приём категории от LLM при confidence ≥ 0.9, иначе → очередь «на подтверждение» (`category_source='llm_pending_review'`)
- Правила детерминированные и тестируются на РЕАЛЬНЫХ описаниях (урок: «ЗАРПЛАТА» не ловит «ЗАРАБОТНАЯ»)
- Правка юзера → merchant_cache (выигрывает над LLM) + пример в few-shot
- LLM-фолбэк: FreeLLMAPI → OpenRouter fallback → оффлайн (правила работают и без LLM вообще)

## Не делать
- Не кидать сырые суммы REAL/DECIMAL в БД
- Не тестировать через сеть: LLM всегда через стаб в тестах
- Не добавлять pandas/embeddings в этом проекте (для RAG — отдельная вилка)