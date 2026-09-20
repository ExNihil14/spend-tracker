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
- `export.py` — выгрузка CSV (utf-8-sig/«;») и XLSX (openpyxl); read-only, принимает снимок строк.
- `recurring.py` — детекция рекуррингов/подписок (read-only эвристика; критерии — `spec/PIPELINE.md`).
- `suggestions.py` — подсказки keyword-правил из правок (read-only: n-граммы+merchant, пороги n≥3/80%, статусы по taxonomy).
- `llm.py` + `prompts.py` — инжектируемый LLM-слой и промпт-контракты (JSON-выхлоп).
- `routers/api.py` — JSON API; `routers/frontend.py` — htmx-страницы.
- `cli.py` — CLI add/report/import/count.
- `config/settings.toml` — порт, LLM-эндпоинты (primary/fallback/offline), авто-приём conf.
- `config/taxonomy.toml` — 18 категорий + keyword-правила (без кода).

## LLM-маршрут (llm.py; резолв — resolve_providers(), статус — `spendtrack llm-status`)
LLM выключен по умолчанию (без конфига сеть не трогается). Приоритет явного выбора:
1. BYO (SPENDTRACK_LLM_BASE_URL + MODEL + API_KEY) — свой OpenAI-совместимый сервер; единственный
   провайдер, без фолбэков в free-каналы; локальный BYO не требует ALLOW_LOCAL_LLM.
2. Ollama-пресет (SPENDTRACK_LLM_PROVIDER=ollama) — полностью локально (air-gap), модель из `llm.offline`.
3. free-цепочка (осознанный opt-in — ключи; локальные шимы — ещё и SPENDTRACK_ALLOW_LOCAL_LLM=1):
   OpenRouter :free (primary) → FreeLLMAPI (localhost:3001, fallback) → abacus-web shim (127.0.0.1:3201, deepseek).
   Ключ подбирается под URL (openrouter → OPENROUTER-ключ, иначе FreeLLM-ключ).
4. offline: правила/кэш — ядро работает без сети (LLM недоступен → rule-only).

## Ключевые решения (зафиксировано)
- Авто-приём при confidence >= 0.9, иначе `llm_pending_review`.
- Сортировка списка: `?sort=recent` (date DESC, внутри дня `COALESCE(statement_order,id)` DESC) | `?sort=amount` (ABS(amount) DESC); очередь — date ASC, **ABS(amount) DESC**, id ASC (крупные по модулю выше).
- Правка юзера → merchant_cache (выигрывает над LLM) + few-shot пример.
- Лог бакетов confidence для калибровки порога.
- Бюджеты: `budgets` (SQLite, не TOML), одна месячная константа без rollover; расход = знаковая сумма месяца
  (возвраты уменьшают); `income`/`transfers` исключены (`BUDGET_EXCLUDED`); rename/delete категории мигрируют бюджет.
- Рекурринги: read-only, вычисляются на лету (без таблиц/состояния); критерии и границы — `spec/PIPELINE.md`;
  «цена» — медиана кластера сумм (±5%), не последний платёж.
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