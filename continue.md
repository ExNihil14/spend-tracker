# Continue.md — состояние проекта Spendtrack

Обновляй ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга:
состояние живёт в файле, а не в истории диалога). Резюмируй короче pre-commit.

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + htmx + SQLite + Tailwind.
- Репозиторий: `D:\dev\personal\spend-tracker` (public, https://github.com/ExNihil14/spend-tracker).
- Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- IDE: VS Code 1.137 + 13 расширений (Ruff, Pylance, официальный FastAPI, Playwright, Jinja2, htmx-toolkit, SQLite viewer, TOML, GitLens, Tailwind, EditorConfig, dotenv, Error Lens). Настройки в `.vscode/` (в репо): Ruff-форматтер Python, Pylance `standard`, pytest Test Explorer.
- Готово: Фаза B, импорт банка (Work 2, `422a56f`), circuit breaker+E2E (`833c48c`),
  очередь подтверждения (Work 3, `0b746d6` + e2e-хвост `511b630`), /settings Фазы 1-2 (категории/тестер `c9c42c4`,
  правила `973d280`). **143 unit + 13 e2e зелёные.**
- ✅ **README под практики 2026 + фиксы** (`2872bae`, `c58dcf0`, `6d01458`, запушены): структура-«шлюз», 3 скриншота
  `assets/`, `.env` теперь читается (`env_file` в `config.py` + `tests/test_config.py`), бейдж «Подтвердить» на
  `/settings` (был 0), `LICENSE` (MIT). Ресёрч-дайджест: `D:\dev\docs\machine\README_BEST_PRACTICES_2026.md`.
- ✅ **Codespaces-стенд работает** (запущен юзером, записи через `review_demo.py seed` / импорт синтетики). Фикс авто-старта
  `1c684e4` (start-app.sh + postAttach; требует Rebuild Container). Ресёрч: `D:\dev\docs\machine\RESEARCH_HOSTING_SPENDTRACKER.md`
  (① Codespaces; ② Render/Tailscale — компромиссы).
- ✅ **UI-пикеры** (`efe7cc7`): `cursor:pointer` + тёмная схема popup (`color-scheme: dark`), accent-color, индикатор
  календаря; e2e расширен (cursor + colorScheme). Ресёрч date-picker: `D:\dev\docs\machine\RESEARCH_DATEPICKER_SPENDTRACKER.md`
  (вердикт — нативный; кастом №1 Air Datepicker, №2 Vanilla Calendar Pro — если после смоука захочется).
- ⏳ **WIP: бюджеты по категориям** (дизайн `EXPERT_BUDGETS_DESIGN.md`): миграция v4 `budgets`, редактор в `/settings`,
  бары «Бюджеты месяца» на `/dashboard`, `GET /api/budgets`, CLI `spendtrack budget`; rename/delete мигрируют бюджет.
  Отклонено (по дизайну): rollover, месячные переопределения, уведомления. **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0):
  GO с правками — принят клэмп `max(0, spent)` для pct/remaining/over, hardening очистки бюджета при delete, граничные
  тесты; P0/P1 частично отклонены фактами** (таблица создаётся до `_migrate`; Store-валидация — слой repo; порядок
  save→clear безопаснее). Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_BUDGETS_OR.md`. Тесты: 156 unit + 15 e2e. Ждёт коммита.
- ✅ **Anti-freeze фикс (15.09):** `D:\dev\bootstrap\scripts\start-detached.ps1` — запуск долгоживущих процессов
  через WMI (`Win32_Process.Create`) ВНЕ job-объекта bash-тула: лаунчер возвращается за 1с (Start-Process висел
  до таймаута 60-120с). Правило обновлено в глобальном `AGENTS.md` + `ANTI_FREEZE_RUNBOOK.md`; проверено dummy-процессом.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO с правками — по P0.1 скрипт переписан на temp-`.ps1`
  (нет интерполяции CommandLine, кавычки/пробелы ок) + логи UTF-8; остальные P0/P1 ревьюера — false positives
  (entry point/`.gitignore`/ссылки проверены фактами).** Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_README_OR.md`.
- ✅ **Калибровка порога 0.9 — инструмент готов** (`reports.confidence_calibration` +
  CLI `uv run python -m spendtrack.cli confidence`): бакеты conf с согласием/исправлениями человека + кандидатные
  пороги 0.4–0.9 (покрытие и % ошибок). Live по проду: LLM-предложений 8, решено 2 (1 исправлен), в очереди 6 →
  «данных мало (<20), оценка ориентировочная». Гонять по мере накопления; решение по порогу — когда решённых ≥20.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO с правками — приняты guard `category_llm != ''` и
  числовая сортировка бакетов (+2 теста); P0 про NULL/CI-тест отклонены фактами** (NOT NULL-колонка; тест видит ту же БД).
  Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_CONFIDENCE_OR.md`.
- ✅ **/settings Фаза 3 — переименование категории** (`2e12d6c`, ждёт push): preview с числом затронутых строк →
  подтверждение → миграция TOML (имя + правила) + БД (transactions.category/category_llm, merchant_cache, examples)
  одной транзакцией; откат БД при сбое TOML; аудит-сбой больше не роняет операцию.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO с правками — P1.4 (same-name) и P1.6 (preview hash) применены;
  P0-замечания отклонены как false positives после верификации** (мёртвые SQLite-таблицы; ключ merchant_cache не зависит
  от категории). Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_SETTINGS_PHASE3_OR.md`.

## Что сделано
- Ядро детерминированное оффлайн: `store.py` (SQLite, WAL, копейки INTEGER),
  `categorize.py` (rule → LLM → validation → queue), `csv_import.py` (BANKS-адаптеры),
  `reports.py`, `llm.py` + `prompts.py` (free models), `routers/`, `cli.py`.
- Тесты: **96 unit + 10 e2e** (Playwright), все оффлайн (LLM инжектируемый стаб).
- 18 категорий + keyword-правила в `config/taxonomy.toml` (правятся без кода).
- Fingerprint-дедуп `sha1(date|amount|desc|account_anon|export_rowid)` — повторный импорт no-op.
- LLM-фолбэк (канон — `spec/ARCHITECTURE.md` §LLM-маршрут): OpenRouter :free → FreeLLMAPI (резерв, WSL на паузе) → **DeepSeek V4.1 Flash (abacus-web shim, порт 3201)** → оффлайн (правила работают и без LLM).
- Авто-приём категории при confidence ≥ 0.9, иначе `llm_pending_review` → очередь.
- Лог бакетов confidence (для калибровки порога).
- UI: Tailwind v4 vendored (static/tailwind.js), card-summary, stripes, responsive grid.

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
> **АКТУАЛЬНО (15.09): 156 unit + 15 e2e зелёные, ruff чист; `main = origin/main = 23ceeed`. WIP: бюджеты по категориям (ревью OpenRouter пройдено) — ждёт команды на коммит.** Ниже — исторические снимки; цифры в них не актуальны.
> **✅ ФАЗА 2 /settings — ПРАВИЛА В UI (15.09):** `POST /settings/rules` (add в конец), `/delete`, `/move` (up/down swap),
> `/preview` (live-превью дублей/перекрытия, debounce 400мс). Вся запись через общий `save()` — атомарно + `.bak` + аудит
> (`add_rule|delete_rule|move_rule`) + конфликт-хэш. Диагностика `analyze_rules`: мёртвые = нет категории / дубль /
> перехвачено более ранним правилом-подстрокой (first-match) + обратное «перекрывает #…»; сверху сводка.
> **Эксперт-ревью (arch-reviewer, deepseek-v4-pro) — GO с правками, P1 закрыт:** перехватчиком в диагностике считается
> только runtime-валидное правило (рантайм пропускает битые категории) + тестер больше не показывает winner из битого
> правила; закрыты пробелы (`.bak` = предыдущая версия, MAX_RULES, lowercase round-trip). Артефакт:
> `D:\dev\docs\machine\EXPERT_REVIEW_SETTINGS_PHASE2.md` (P2-бэклог: audit не должен ронять операцию, parse-back контентом и др.).
> **Попутно починен латентный баг Фазы 1:** partials не содержали свои обёртки `#settings-categories/#settings-rules`,
> из-за чего вторая операция без перезагрузки не находила htmx-target. E2E теперь изолирует taxonomy (`SPENDTRACK_TAXONOMY`,
> tmp-копия + восстановление) — прод-конфиг не трогается. **Live NSSM:** диагностика нашла реальное мёртвое правило
> в проде (#23 «ЗАРАБОТНАЯ ПЛАТА» перекрыто #21 «ЗАРАБОТНАЯ»), превью вернуло «дубль + будет мёртвым». Дизайн-док обновлён.
> **Импорт провалидирован синтетикой** (реальных выписок нет): `tests/synth_bank.py` (seeded-генератор sber/tinkoff/yandex) + `tests/test_synth_import.py`; critical-фикс дедупа (occurrence вместо позиции строки — реэкспорт со сдвигом не дублирует). Стратегия: `D:\dev\docs\machine\TEST_DATA_STRATEGY.md`.
- ✅ **Фаза B закоммичена (77a25dc)**: дашборды (Chart.js+htmx), URL-фильтры hx-push-url, hx-boost, фикс формы добавления (JSON+form, HX-ветка HTML), deepseek-фолбэк, spec/ A+PIPELINE+stack. **43 passed, ruff чист, рабочее дерево чистое** — практика №3 MASTER_PLAN «commit перед задачей, diff после» выполнена.
- ✅ mattpocock/skills audit (13.09): всё внедрённое используется.
- ⏳ Визуальный smoke `/approve` в браузере юзера (план: `spec/QA_APPROVE_SMOKE.md`, демо-данные `scripts/review_demo.py seed`).
- ✅ Пробелы MASTER_PLAN закрыты/пересмотрены: perf-маркер с JSON закрыт (`75f8165`, `reports/perf.json`, маркер в pyproject); Hoppscotch/Capture MCP — **отклонены** (SPENDRACK_PRIORITIES_REVIEW); Фаза 4 закрыта (v0.1.0, remote, защита `main`).
- ✅ **Сортировка транзакций (14.09):** режимы `recent` (дата DESC; внутри дня — `statement_order` из выписки, иначе id) и `amount` (|сумма| DESC) с URL-состоянием `?sort=`; миграция v3 (`statement_order`), импорт заполняет порядок строк; фильтры/месяц сохраняют sort.
- ✅ **Группировка по дням (15.09):** в режиме «recent» — заголовок дня `ДД.ММ.ГГГГ` + итог за день (цвет по знаку); в «крупные сначала» — плоский список. **Keyset-scroll осознанно отложен:** список помесячный, лимит 500 покрывает месяц; вернуться при мультимесячном режиме.
- ✅ **Словарь мерчантов + точность правил:** `tests/merchants.py` (27 реалистичных брендов/формулировок) + `tests/test_rules_accuracy.py` — покрытие keyword-правил **100%** (оффлайн).
- ✅ **Keyset-пагинация по дням (15.09):** `list_transactions_days` + `partials/tx_rows.html` + `/transactions/more` + sentinel (`hx-trigger="revealed"`) — готовность к большим спискам без разрезания дней/итогов; месяцу хватает одной страницы (PAGE_DAYS=31). Виртуализация `<table>` отклонена (анализ: `D:\dev\docs\machine\VIRTUALIZATION_ANALYSIS.md`); Фаза 2 (div-grid + content-visibility / TanStack Virtual) — по триггеру «все месяцы + >5K узлов».
- ✅ **Toast-подтверждение (15.09):** OOB-тост «Одобрено: <категория> — <описание>» / «Пропущено: …» / «Одобрено записей: N» (`aria-live`, авто-скрытие 1.8с).
- ⏭ Следующее по ROI: визуальный smoke `/settings` в браузере юзера → калибровка порога 0.9 по бакетам
  confidence (данные копятся) → бюджеты по категориям. Из Фазы 4 дизайна — merge категорий (по запросу).
- ✅ Стилизация UI Tailwind завершена (13.09.2026): `base.html` + `index.html` + `approve.html` — утилитарные классы Tailwind v4 vendored (282KB static/tailwind.js), card-style summary, table stripes, responsive grid. Всё рендерится: smoke-тест 200 OK.
- ✅ DeepSeek-категоризация добавлена третьим фолбэком (OpenRouter → FreeLLMAPI → **abacus-web shim:3201/deepseek-v4-1-flash** → offline). Токен TTL 1ч. **Проверена ЖИВЫМ вызовом: «МАГНИТ» → groceries, conf 0.96.**
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
5. ✅ Фаза B: дашборды (Chart.js + htmx), URL-фильтры `hx-push-url`, hx-boost/OOB-свапы (`77a25dc`).
6. ✅ Импорт банка (Work 2, `422a56f`) + circuit breaker/Playwright E2E (`833c48c`).
7. ✅ Очередь подтверждения категоризации (Work 3, `0b746d6`) + e2e `/approve` (`511b630`).
   Единый фрагмент очереди `partials/review_rows.html`, все действия через `_rows_html`+OOB.
8. ✅ Категории (`c9c42c4`), правила (Фаза 2, `973d280`), переименование категорий (Фаза 3, WIP) в UI.
   Далее: визуальный smoke `/settings` в браузере юзера, калибровка порога 0.9, затем бюджеты (когда данные чистые).

## Мета
- Возврат к работе: просто прочитай эти файлы: AGENTS.md (команды), CONTEXT.md (словарь),
  spec/ (детали), continue.md (статус).