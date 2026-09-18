# Spendtrack — AGENTS.md

## Что это
Трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx, offline-first детерминированное ядро, LLM-шов только для остатка (~30-40% транзакций).

## Обязательные файлы в начале сессии
- `continue.md` — состояние проекта и следующие шаги (источник для продолжения работы).
- `spec/ARCHITECTURE.md` — архитектура/решения/план (источник истины).
- `CONTEXT.md` — словарь терминов (не перифразировать).
- `spec/PIPELINE.md` + `spec/stack.md` — команды/контур верификации и стек.
- `spec/QA_APPROVE_SMOKE.md` — QA-план очереди `/approve` (читать при работах по очереди/категоризации).
- Мастер-план из `D:\dev\docs\vibecoding\out_analysis\MASTER_PLAN.md` — практики/грабли/промпты (читай spec-раздел при изменениях).

## Команды
- Тест: `uv run pytest`
- Линт: `uv run ruff check src tests`
- Запуск: `uv run uvicorn spendtrack.main:app --port 8766` (или `.\run.ps1`)
- CLI: `uv run python -m spendtrack.cli add -23.45 "milk"` / `report` / `import file.csv --bank auto` / `count` / `confidence` (калибровка порога 0.9) / `budget` (прогресс по бюджетам) / `doctor` (целостность) / `recurring` (рекурринги/подписки) / `suggest-rules` (подсказки правил из правок) / `digest` (дайджест недели + аномалии)
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
- Авто-приём категории от LLM при confidence ≥ 0.9, иначе → очередь «на подтверждение» (`review_status='pending'`, `category_llm` = предложение LLM)
- Правила детерминированные и тестируются на РЕАЛЬНЫХ описаниях (урок: «ЗАРПЛАТА» не ловит «ЗАРАБОТНАЯ»)
- Правка юзера → merchant_cache (выигрывает над LLM) + пример в few-shot
- LLM-фолбэк (канон — `spec/ARCHITECTURE.md` §LLM-маршрут): OpenRouter :free → FreeLLMAPI (резерв) → abacus-web shim (deepseek) → офлайн-правила (работают и без LLM вообще)

## Не делать
- Не кидать сырые суммы REAL/DECIMAL в БД
- Не тестировать через сеть: LLM всегда через стаб в тестах
- Не добавлять pandas/embeddings в этом проекте (для RAG — отдельная вилка)

## Git-процесс (обязательно, из GIT_WORKFLOW_RECOMMENDATIONS.md)
- Стратегия: trunk-based + короткие feature-ветки. `main` — единственная долгоживущая, всегда зелёная. НЕ создавать develop/release/*/hotfix/*.
- Ветки: `feature/<slug>` (1-3 дня), `fix/<slug>`, `chore/<slug>`; после merge — `git branch -d`.
- НЕ коммитить без явной команды пользователя. НЕ пушить без отдельной явной команды.
- Перед коммитом: `uv run pytest && uv run ruff check`. Красные тесты — не коммитить.
- Один коммит = один смысловой блок (Conventional Commits, тип(scope): тело). Не смешивать рефакторинг и фичу.
- Merge в main: `git rebase main` → `git switch main && git merge --ff-only`. Не делать merge-коммиты.
- Squash только для wip/fix-опечаток; осмысленные тематические коммиты — оставлять.
- НИКОГДА `git push --force` и `git reset --hard` на main. Только на своей feature-ветке и с подтверждения.
- НЕ коммитить: .env, data/, *.sqlite, ключи, токены.
- Версии: SemVer `0.x.y` + аннотированные теги (git tag -a v0.1.0 -m "..."). CHANGELOG.md — из Conventional Commits.
- Перед отчётом о готовности: показать `git status` и `git diff --stat` (факт, не слова).