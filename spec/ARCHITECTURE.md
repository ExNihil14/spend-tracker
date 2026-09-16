# SPEC: Архитектура Spendtrack

Источник истины для агентов. Код — трансляция этой спеки; расхождение кода и спеки
возвращается в спеку (правило двунаправленного цикла из MASTER_PLAN.md).

## Принципы
1. Ядро детерминированное и оффлайн; LLM — единственный «шов», всегда инжектируемый в тесты.
2. Суммы — `amount_kopecks INTEGER` (копейки); `parse_amount→int`, `fmt_amount→"−123.45"`.
3. Категоризация каскадом: keyword-правила → merchant_cache → LLM → очередь подтверждения.
4. Дедуп импорта через fingerprint: повторный импорт = no-op.
5. Без pandas/embeddings в этом проекте (для RAG — отдельная вилка).

## Компоненты
- `main.py` — FastAPI-приложение, монтирует routers/, склеивает store+llm.
- `store.py` — SQLite (WAL). Таблицы: transactions, categories, merchant_cache,
  account_pseudonyms, import_batches, examples, budgets (лимиты по категориям, v4), (log buckets confidence).
- `categorize.py` — конвейер категоризации (rule→llm→validation→queue), `classify_with_injectable`.
- `csv_import.py` — импорт CSV по банкам (BANKS-адаптеры), fingerprint-дедуп.
- `reports.py` — агрегаты по периодам/категориям.
- `llm.py` + `prompts.py` — инжектируемый LLM-слой и промпт-контракты (JSON-выхлоп).
- `routers/api.py` — JSON API; `routers/frontend.py` — htmx-страницы.
- `cli.py` — CLI add/report/import/count.
- `config/settings.toml` — порт, LLM-эндпоинты (primary/fallback/offline), авто-приём conf.
- `config/taxonomy.toml` — 18 категорий + keyword-правила (без кода).

## LLM-маршрут (порядок попыток в llm.py)
1. primary: живой free-канал — сейчас OpenRouter :free (nemotron-3-super-120b).
2. fallback: FreeLLMAPI (localhost:3001, Z.AI glm-4.5-flash; резерв, WSL на паузе).
3. deepseek: abacus-web shim (127.0.0.1:3201, deepseek-v4-1-flash, 0 кредитов, 1M ctx; пауза до 20.09).
4. offline: правила/кэш — ядро работает без сети (LLM недоступен → rule-only).

## Ключевые решения (зафиксировано)
- Авто-приём при confidence >= 0.9, иначе `llm_pending_review`.
- Сортировка списка: `?sort=recent` (date DESC, внутри дня `COALESCE(statement_order,id)` DESC) | `?sort=amount` (ABS(amount) DESC); очередь — date ASC, **ABS(amount) DESC**, id ASC (крупные по модулю выше).
- Правка юзера → merchant_cache (выигрывает над LLM) + few-shot пример.
- Лог бакетов confidence для калибровки порога.
- Бюджеты: `budgets` (SQLite, не TOML), одна месячная константа без rollover; расход = знаковая сумма месяца
  (возвраты уменьшают); `income`/`transfers` исключены (`BUDGET_EXCLUDED`); rename/delete категории мигрируют бюджет.
- Запуск: `uv run uvicorn spendtrack.main:app --port 8766` (или run.ps1).

## План (из MASTER_PLAN.md, Фаза A/B)
- A1 ✅ стилизация UI Tailwind + верификация в браузере.
- A2 ✅ категоризация через бесплатный DeepSeek (abacus-web shim 3201) третьим фолбэком.
- A3 ✅ форма подтверждения (Work 3: `/approve`, approve/skip/approve-all, `review_status`), негативные сценарии (TC-12..14).
- B ✅ дашборды (Chart.js + htmx), URL-фильтры через hx-push-url, hx-boost + OOB-свапы.

## Фаза B (реализовано 13.09)
- **Роут `/dashboard`** (`routers/frontend.py`): bar по дням (report_daily) + doughnut по категориям,
  данные из `reports.py`, Chart.js vendored (`static/chart.umd.min.js`, v4.4.7), цвета из `cat_colors`.
- **URL-фильтры**: index-роут принимает `category` и `q`; фильтр-бар в `index.html` шлёт `hx-get`
  с `hx-push-url` (состояние в URL); `store.list_transactions(..., search=None)` фильтрует по описанию/мерчанту.
- **hx-boost**: `base.html` — `<body hx-boost="true">`, meta `htmx-config` historyCacheSize=0,
  навигация по страницам без полной перезагрузки.
- **OOB-свап/счётчик**: `#pending-count` обновляется `hx-swap-oob` из ответов approve/skip/approve-all
  (Work 3, `511b630`); `GET /api/pending-count` — JSON для внешних проверок.
- **Форма добавления** (`index.html`): `hx-post` → `/api/transactions`; эндпоинт принимает И JSON,
  И form-urlencoded (по content-type); при `HX-Request: true` возвращает HTML-фрагмент в `#newmsg`
  вместо JSON; overlay `#global-indicator` (htmx-indicator) во время запроса; после успеха — reset формы,
  обновление `#pending-count` и таблицы (`hx-trigger="refresh-list from:body"` на `#tx-table`).
- **Тесты**: `report_daily` в `reports.py` + тесты; API-тесты JSON/form/HX-ветка; итого **79 unit + 10 e2e**, ruff чист (CI: `.github/workflows/ci.yml`).