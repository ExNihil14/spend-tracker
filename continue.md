# Continue.md — состояние проекта Spendtrack

Обновляй ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга:
состояние живёт в файле, а не в истории диалога). Резюмируй короче pre-commit.

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + htmx + SQLite + Tailwind.
- Репозиторий: `D:\dev\personal\spend-tracker` (один коммит: `cadea35 scaffold`).
- Стек: uv/Python 3.13, pytest, ruff.

## Что сделано
- Ядро детерминированное оффлайн: `store.py` (SQLite, WAL, копейки INTEGER),
  `categorize.py` (rule → LLM → validation → queue), `csv_import.py` (BANKS-адаптеры),
  `reports.py`, `llm.py` + `prompts.py` (free models), `routers/`, `cli.py`.
- 18 категорий + keyword-правила в `config/taxonomy.toml` (правятся без кода).
- Fingerprint-дедуп `sha1(date|amount|desc|account_anon|export_rowid)` — повторный импорт no-op.
- LLM-фолбэк: FreeLLMAPI → OpenRouter :free → **DeepSeek V4.1 Flash (abacus-web shim, порт 3201, 0 кредитов)** → оффлайн (правила работают и без LLM).
- Авто-приём категории при confidence ≥ 0.9, иначе `llm_pending_review` → очередь.
- Лог бакетов confidence (для калибровки порога).
- UI: Tailwind v4 vendored (static/tailwind.js), card-summary, stripes, responsive grid.
- 35 тестов (оффлайн, LLM инжектируемый).

## Архитектурные решения (зафиксировано, менять только через spec/review)
- Суммы = `amount_kopecks INTEGER` (копейки), НЕ REAL/DECIMAL.
- Проект без pandas/embeddings — для RAG отдельная вилка.
- тесты не ходят в сеть: LLM всегда стаб.

## Git-процесс (принято 13.09, из GIT_WORKFLOW_RECOMMENDATIONS.md — DeepSeek v4.1 Flash)
- Trunk-based + короткие feature-ветки: `main` (всегда зелёная) + `feature/<slug>` / `fix/<slug>` / `chore/<slug>`.
- НИКАКИХ develop/release/hotfix для solo. Merge: `git rebase main` → `--ff-only`. Squash только wip.
- Один публичный репо; `data/` (SQLite с расходами) + `.env` полностью вне git (gitignore расширен).
- SemVer `0.x.y` + аннотированные теги; CHANGELOG.md из Conventional Commits (когда понадобится).
- Правила для агента — в AGENTS.md (не коммитить/пушить без явной команды, pytest+ruff перед коммитом).
- Полный отчёт: `D:\dev\docs\machine\GIT_WORKFLOW_RECOMMENDATIONS.md`.
- ✅ **ОПУБЛИКОВАНО 13.09**: remote origin = https://github.com/ExNihil14/spend-tracker (public), ветка `master`→`main` переименована, первый push сделан, vanity: gh CLI установлен (v2.100.0, PATH: C:\Program Files\GitHub CLI\gh.exe), авторизация ExNihil14 (OAuth, repo scope).
- ✅ **Защита main на GitHub**: force-push запрещён, deletions запрещены, required_linear_history (только --ff-only), enforce_admins=true. PR-ритуал не обязателен для solo (см. отчёт, п.9).

## Что активно / в работе
- ✅ **Фаза B закоммичена (77a25dc)**: дашборды (Chart.js+htmx), URL-фильтры hx-push-url, hx-boost, фикс формы добавления (JSON+form, HX-ветка HTML), deepseek-фолбэк, spec/ A+PIPELINE+stack. **43 passed, ruff чист, рабочее дерево чистое** — практика №3 MASTER_PLAN «commit перед задачей, diff после» выполнена.
- ✅ mattpocock/skills audit (13.09): всё внедрённое используется.
- ⏳ Сверить API-клиент с HX-фрагментом и модалкой в браузере юзера (последний визуальный smoke).
- Открытые пробелы MASTER_PLAN: perf-маркер с JSON-выводом (Фаза 2), Hoppscotch-коллекция + Capture MCP скриншоты (Фаза 3), .env.local + remote + защита ветки (Фаза 4 — почти не начата).
- ✅ Стилизация UI Tailwind завершена (13.09.2026): `base.html` + `index.html` + `approve.html` — утилитарные классы Tailwind v4 vendored (282KB static/tailwind.js), card-style summary, table stripes, responsive grid. Всё рендерится: smoke-тест 200 OK.
- ✅ DeepSeek-категоризация добавлена третьим фолбэком в `llm.py` (FreeLLMAPI → OpenRouter → **abacus-web shim:3201/deepseek-v4-1-flash** → offline). Токен TTL 1ч. **Проверена ЖИВЫМ вызовом: «МАГНИТ» → groceries, conf 0.96, source=deepseek.**
- ✅ Контур верификации: `tests/test_fallback.py` (порядок primary→fallback→deepseek с моком, оффлайн), итого **37 passed**, ruff чист.
- ✅ **Фаза 2 smoke-тест полного сценария (13.09)**: dev-сервер UP + shim UP → POST /api/transactions (live deepseek, conf 0.35 → llm_pending_review) → GET / (htmx: строка транзакции, бейдж категории, источник+conf, счётчик «Подтвердить»=1). Тестовая запись удалена после проверки.
- ✅ **Фаза 1 (фундамент контекста)**: spec/ теперь содержит ARCHITECTURE.md + stack.md (стек/версии/LLM-маршрут) + PIPELINE.md (команды, контур верификации, аддитивные миграции).

## Stack-вердикт (13.09.2026, анализ с фокусом на 2026-исследования)
**Остаёмся на htmx + FastAPI + SQLite.** React + TS переходит ТОЛЬКО при: >3 concurrent users / offline-first / rich-интерактив (drag-drop, real-time charts) / команда >2 человек (оценка миграции: 80-120ч, обнулит 37 тестов).
- React+TS vs htmx → **htmx** (85%): CRUD-heavy, htmx даёт ~80% UX React за 20% сложности.
- TanStack Query vs htmx data-fetching → **htmx** (80%): наш state серверный (SQLite), client-side кэш не нужен.
- TanStack Router vs React Router v7 → **TanStack Router** (70%, только если React): TS-first, Zod-валидация search params, loader typing.
- FastAPI vs Node → **FastAPI** (90%). SQLite vs PostgreSQL → **SQLite/WAL** (95%).
- НЕ использовать: PostgreSQL, Redis, GraphQL, Docker, Next/Remix (SSR не нужен), microservices.
- Ближайшие улучшения htmx: `hx-boost` (плавные переходы), OOB swap (динамика счётчиков), фильтры в URL через `hx-push-url`, дашборды (Chart.js + htmx).

## Известные ограничения/грабли
- Правка юзера → merchant_cache + few-shot (правит будущий импорт).
- Не запускать qwen 7b одновременно с dev-сервером (GTX 1050 4GB).
- Стройные проверки: «готово» без фактической проверки не принимается.

## Следующие шаги (приоритет — Фаза A/B из MASTER_PLAN.md)
1. ✅ Стилизация UI Tailwind завершена (13.09).
2. ✅ DeepSeek-категоризация (третий фолбэк) — реализована + живая проверка + тест порядка фолбэков.
3. ✅ Live-категоризация в UI (browser-проверка, Фаза 2 smoke): POST /api/transactions → deepseek (conf 0.35, llm_pending_review) → GET / htmx-отображение (бейдж категории, источник+conf, счётчик «Подтвердить»). Проверено через curl, тестовая запись удалена.
4. ✅ spec/: ARCHITECTURE.md + stack.md + PIPELINE.md (Фаза 1 MASTER_PLAN — фундамент контекста).
5. Фаза B: дашборды (Chart.js + htmx), URL-фильтры `hx-push-url`, hx-boost/OOB-свапы.

## Мета
- Возврат к работе: просто прочитай эти файлы: AGENTS.md (команды), CONTEXT.md (словарь),
  spec/ (детали), continue.md (статус).