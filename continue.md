# Continue.md — состояние проекта Spendtrack

Обновляй ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга:
состояние живёт в файле, а не в истории диалога). Резюмируй короче pre-commit.

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + htmx + SQLite + Tailwind.
- Репозиторий: `D:\dev\personal\spend-tracker` (public, https://github.com/ExNihil14/spend-tracker).
- Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- IDE: VS Code 1.137 + 13 расширений (Ruff, Pylance, официальный FastAPI, Playwright, Jinja2, htmx-toolkit, SQLite viewer, TOML, GitLens, Tailwind, EditorConfig, dotenv, Error Lens). Настройки в `.vscode/` (в репо): Ruff-форматтер Python, Pylance `standard`, pytest Test Explorer.
- Готово: Фаза B, импорт банка (Work 2, `422a56f`), circuit breaker+E2E (`833c48c`),
  очередь подтверждения (Work 3, `0b746d6` + e2e-хвост `511b630`), /settings Фазы 1-3 (категории `c9c42c4`,
  правила `973d280`, переименование `2e12d6c`), README/фиксы (`6d01458`), Codespaces (`1c684e4`), пикеры (`efe7cc7`),
  калибровка (`7f2ed66`), бюджеты (`73cc5fa`), фикс дашборда (`3076473`), CI e2e-джоб (`e5b13ac`).
  **252 unit + 18 e2e зелёные** (см. «АКТУАЛЬНО»).
- ✅ **README под практики 2026 + фиксы** (`2872bae`, `c58dcf0`, `6d01458`, запушены): структура-«шлюз», 3 скриншота
  `assets/`, `.env` теперь читается (`env_file` в `config.py` + `tests/test_config.py`), бейдж «Подтвердить» на
  `/settings` (был 0), `LICENSE` (MIT). Ресёрч-дайджест: `D:\dev\docs\machine\README_BEST_PRACTICES_2026.md`.
- ✅ **Codespaces-стенд работает** (запущен юзером, записи через `review_demo.py seed` / импорт синтетики). Фикс авто-старта
  `1c684e4` (start-app.sh + postAttach; требует Rebuild Container). Ресёрч: `D:\dev\docs\machine\RESEARCH_HOSTING_SPENDTRACKER.md`
  (① Codespaces; ② Render/Tailscale — компромиссы).
- ✅ **UI-пикеры** (`efe7cc7`): `cursor:pointer` + тёмная схема popup (`color-scheme: dark`), accent-color, индикатор
  календаря; e2e расширен (cursor + colorScheme). Ресёрч date-picker: `D:\dev\docs\machine\RESEARCH_DATEPICKER_SPENDTRACKER.md`
  (вердикт — нативный; кастом №1 Air Datepicker, №2 Vanilla Calendar Pro — если после смоука захочется).
- ✅ **Бюджеты по категориям** (`73cc5fa`, запушено; дизайн `EXPERT_BUDGETS_DESIGN.md`): миграция v4 `budgets`,
  редактор в `/settings`, бары «Бюджеты месяца» на `/dashboard`, `GET /api/budgets`, CLI `spendtrack budget`;
  rename/delete мигрируют бюджет. Отклонено: rollover, месячные переопределения, уведомления.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO — приняты клэмп `max(0, spent)`, hardening clear_budget,
  граничные тесты; часть P0/P1 отклонена фактами** (`EXPERT_REVIEW_BUDGETS_OR.md`).
  **Прод-NSSM актуален с 16.09 13:08** (`nssm restart spendtrack`; v4 применена, `/api/budgets` 200, стрелки дашборда абсолютные).
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
> **АКТУАЛЬНО (19.09, вечер-2): автоматизация + демо-режим + стратегия рынка + AGPLv3.** ① Автогейт контракт-дельты
> (`scripts/contract_delta.py`, CI-шаг) и one-command ревью (`scripts/review.py`) — **289 unit**, коммиты `a3f1871`/`d0e5c83`;
> ② **демо-режим** (`scripts/demo_data.py`: 350 tx, 6 подписок, 3 типа аномалий, 6 pending, 5 бюджетов; Codespaces-автосид,
> стенд 8767) — `0f80e5c`/`d81c369`; ③ **рынок**: `RESEARCH_SPENDTRACKER_MARKET.md` (46 источников) + `EXPERT_STRATEGY_...`;
> решения — **AGPLv3**, **RU-first**, валидация «10 CSV» → лендинг-запуск, Boosty (11.7%); ④ **волна 3 расширена рыночными
> S-задачами:** экспорт CSV/Excel, one-command установка (Docker/uvx), лендинг + демо-кнопка (Codespaces), BYO-LLM/Ollama;
> ⑤ i18n/локализация/юр/a11y — `D:\dev\docs\machine\DESIGN_I18N_LEGAL_A11Y.md`. **Ждут коммита: LICENSE (AGPLv3) + README
> (Для кого/EN/поддержка) + continue.md.** Push — юзера (ahead: см. git status).
> **АКТУАЛЬНО (19.09): тяжёлый one-shot экспертный анализ проекта + роадмапа выполнен (Abacus, claude-opus-5).**
> Артефакт: `D:\dev\docs\machine\EXPERT_ANALYSIS_SPENDTRACKER_ABACUS.md` (протокол отбора модели + факт-чек P0 + полный отчёт).
> Прогон: 1 запрос, 110 с, 2990 in / 5910 out ≈ $0.175 ≈ 0.9% месячного лимита Abacus; рекурсии нет. Ключевые выводы:
> ① «фичи опережают данные» (в проде 8 tx; recurring/digest/калибровка data-gated) → **рекомендация: волна 3 = Telegram
> quick-capture как канал данных** (при неприятии приватности — PWA-быстрый ввод), merge категорий попутно, цели/net worth
> отложить до ≥3 мес истории; ② P0-долг: `busy_timeout` (WAL/`foreign_keys` уже есть), restore-drill бэкапа + копия вне
> ноутбука, gitleaks в CI, кламп confidence/лимит длины LLM-входа; ③ evals-контур: golden-набор ~100+ merchant-строк →
> оффлайн-калибровка порога 0.9 без ожидания прода. Наш факт-чек: тезис про fingerprint/`export_rowid` частично отклонён
> (дедуп уже hardening’ен 15.09 — индекс повторяемости), остальное принято. **Контр-мнение (Gemini 3.1 Pro, 1 запрос ≈$0.027, адъюдикация — в артефакте §5):** долг ДО фичи; **PWA-ввод предпочтительнее Telegram** (ноутбук спит — long-polling вне дома не работает; у TG-варианта апдейты копятся в облаке, но «мгновенного захвата» нет); И3 (evals на синтетике) урезать до smoke-калибровки; sync+идемпотентность обязательно в DoD ввода. **Итог двух моделей: сначала P0-долг (S) → канал данных с PWA-уклоном (M) → merge/bulk попутно. Решение юзера; без команды не реализуем.**
> **Исполнитель реализации (роутинг 19.09, артефакт §3a):** основной — `opencode-go/deepseek-v4.1-flash` (все волны 1–2 на нём);
> эскалация волны 3 при провале — `opencode-go/deepseek-v4-pro` (SWE-V 80.6/TB2 67.9, та же семья, новый чат, ≤2/нед),
> альтернатива `glm-5.3`; Abacus-флагманы — только one-shot дизайн-чек (~$0.05), не исполнители.
> **P0-долг РЕАЛИЗОВАН (19.09, субагент flash по ТЗ `TASK_BRIEF_P0_DEBT.md`) и принят оркестратором:**
> busy_timeout/synchronous + pragma-тест; `scripts/restore_drill.py` + doctor-чек `restore_drill` (info/warn/critical) + маркер;
> gitleaks-job в CI; кламп confidence + лимит description 300. **+22 теста → 275 unit, ruff чист.** Live: drill ok
> (count/sum совпали с живой БД), doctor 10/10, `/health/data` 200 (NSSM рестартнут). Ревью $0 (ultra-550b, 77 с): GO;
> **3 P0 из 4 отклонены фактами** (порядок pragmas — замер sync=1; `as_uri?mode=ro` реально read-only; бэкапы — VACUUM INTO
> без `-wal`), P1 применены (tz-конверсия, детерминированный timing, докстринг). Артефакт `EXPERT_REVIEW_P0DEBT_OR.md`.
> **Закоммичен и запушен (`26f9aec`); доки процесса (дисциплина данных) — `cf1064b`. Следующее — волна 3: канал данных с PWA-уклоном.**
> **АКТУАЛЬНО (18.09, вечер): волна 2 — дайджест недели + флаги аномалий (S+S) реализованы и запушены (`d610370`, `8442950`).**
> Ядро `src/spendtrack/digest.py` (read-only, на лету, состояние не хранится): окно rolling `--days N` (дефолт 7) vs прошлое
> окно; расход/доход/баланс + дельта, топ-5 категорий расхода с дельтами, самый дорогой день, средний расход/день,
> pending, ближайшие ожидаемые списания рекуррингов (`next_expected` ≤14 дн; просроченные помечаются), аномалии top-10:
> ① `large_expense` — ≥3× медианы |расходов| категории за 90 дн, ≥10 наблюдений, пол 1000 ₽; ② `price_jump` — первое
> отклоняющееся ≥10% списание после активного рекурринг-кластера (событие смены цены; повторно не флагуется);
> ③ `near_duplicate` — один день + мерчант + |сумма|, ≥2 строк (fingerprint не склеил). Переводы исключены везде,
> доход — только в итогах. CLI `spendtrack digest [--days N] [--json]` + карточка «Дайджест недели» на `/dashboard`.
> **252 unit + 18 e2e зелёные, ruff чист**; live-прогон на прод-БД (в окне пусто — data-gated норма, pending 6), NSSM 8766
> рестартнут, `/health/data` ok, карточка проверена playwright MCP (prod, empty-state). Ревью OpenRouter :free ×2 $0
> (`EXPERT_REVIEW_DIGEST_OR.md`): **все 3 P0 отклонены фактами** (семантика первого скачка, `category NOT NULL`,
> знак Δ расхода), приняты P1 (bound `date<=end`, «просрочено» в CLI, шкалы score, +4 теста). Доки: PIPELINE/CONTEXT/AGENTS.
> **Следующее — волна 3 по выбору юзера:** Telegram quick-capture (M, приватность) / слияние категорий (S) / цели-net worth;
> калибровка 0.9 — 2/20 решённых (data-gated).
> **АКТУАЛЬНО (17.09, вечер): СЕССИЯ ЗАКРЫТА — всё запушено, CI зелёный, MCP-стек активен.**
> `origin/main = 7da8cfe` (8 коммитов: doctor, recurring, suggest-rules, фиксы Codespaces/CI, doctor-hardening, доки);
> CI на последних push: `e2e` + `lint-and-test` зелёные (фикс флейка превью подтверждён). Bootstrap: `9592aeb` (probe-mcp.py).
> **MCP (после рестарта opencode) проверен живыми вызовами:** context7 (FastAPI IDs), memory (граф), **playwright —
> открыл `/dashboard` стенда 8767, карточка «Подписки / рекурринги» найдена («активных 3, −652.00 ₽/мес»)**.
> Бэклог-мелочь: `favicon.ico` 404 в консоли (добавить favicon в `static/` + link в `base.html`).
> **Следующая сессия — волна 2: дайджест недели + флаги аномалий** (S+S; стартер обновлён в `SESSION_START_PROMPT.md`).
> **`suggest-rules` (волна 1 п.3) реализован, отревьюен и закоммичен** (`1b953c4` + doctor-фикс `aa79fb9` + доки `7da8cfe`):
> read-only кандидаты keyword-правил из решений человека (corrections, переопределения LLM в approved-строках, examples,
> тип «merchant»); униграммы/биграммы (UPPER, без цифр, длина 2–64), пороги n≥3/чистота ≥80%, конфликты видны, статусы по
> `analyze_rules` (новое/дубль/мёртвое/пересечение); CLI `spendtrack suggest-rules [--json]`, записей нет. **225 unit зелёные
> (14 в test_suggestions), ruff чист**; live на прод-БД: «решённых строк 1, кандидатов 0» — data-gated норма.
> Ревью :free $0 (ultra NO-GO / super обрезано): приняты — лимит длины паттерна 2–64, верный текст «пересечение»,
> кириллица І/Ї/Ґ/Ў, тип исключения в `_guarded`, +5 тестов; ложный P0 super («двойной счёт при OR») отклонён фактом SQL;
> артефакт `EXPERT_REVIEW_SUGGEST_RULES_OR.md`.
> **Попутный doctor-фикс (найден стрессом флейка):** `_guarded` переводит любое исключение чека в critical,
> `quick_check` корректно обрабатывает «PRAGMA упал» (malformed); тест порчи БД стал детерминированным (rootpage),
> 15/15 в стрессе. Детали — в PIPELINE §Suggest-rules.
> **АКТУАЛЬНО (16.09, ночь): рекурринги/подписки готовы и закоммичены `236525f` (волна 1 п.2; ждёт визуального смоука и push юзера).**
> **Фиксы по следам проверок (16.09 ~22:00, закоммичены):** ① Codespaces-500 на `/dashboard` — воркспейс синкнулся на новый
> коммит при живом старом uvicorn (Jinja горячие, Python нет) → `UndefinedError: 'recurring'`; фикс — `--reload` в
> `.devcontainer/start-app.sh` + README-troubleshooting (`d47e3eb`). ② CI-флейк `test_rule_dead_badge_and_preview`
> (падал в CI с 12:57, к recurring отношения не имеет: гонка дебаунс-запросов превью и пустого фрагмента для паттерна
> <2 символов) — фикс: ожидание своего запроса по `post_data` через `expect_response` (`7bfd16a`).
> Ревью :free $0 — GO без замечаний (`EXPERT_REVIEW_CODESPACES_CI_OR.md`; ultra-550b 3× пустой ответ провайдера,
> вердикт дал super-120b). **Ждут push юзера: `2579e74`, `d47e3eb`, `7bfd16a`** (CI подтвердит фикс флейка после push).
> 209 unit + 17 e2e зелёные, ruff чист. Ядро `src/spendtrack/recurring.py` (read-only, вычисление на лету): кластеры сумм
> ±5% бегущей медианы, ≥3 повторов, интервалы 27–34 дн (медиана 28–31), 1 пропуск месяца (56–62 дн), `active` ≤40 дн;
> только расходы, без transfers; «цена» = медиана кластера (по всем списаниям), категория — самая частая; уникальные дни —
> для интервалов и счётчика. Вывод: CLI `spendtrack recurring [--json]` + карточка «Подписки / рекурринги» на `/dashboard`
> (по всей истории, активные в итог). Ревью ×2 OpenRouter :free ($0, nemotron ultra/super — `EXPERT_REVIEW_RECURRING_OR.md`):
> **P0 отклонены фактами** (cat_colors/fmt есть в контексте), принята правка «цена по всем списаниям кластера» +регресс-тест.
> Live: прод-БД = 0 находок (демо-масштаб — норма); смоук-стенд `http://127.0.0.1:8767/dashboard` (temp-БД, синтетика
> 4 мес: 4 находки / 3 активные, месячный итог −652.00) — ждёт визуальной проверки юзером; прод NSSM рестартнут,
> `/health/data` ok. Доки: PIPELINE/CONTEXT/ARCHITECTURE/AGENTS. Детали смоука: temp\opencode\recurring_smoke\.
> Ниже — предыдущий статус (doctor) и исторические снимки.
> **АКТУАЛЬНО (16.09, вечер): 191 unit + 16 e2e зелёные, ruff чист; doctor закоммичен и запушен** (`0ad83f2` + `a20dcc8` + `1bd36bf`; **origin/main синхронен**), **прод рестартнут — live `/health/data` = 200 `status: ok` (9/9 чеков ok, backup свежий)**. **Фикс CLI-кодировки `2e4c93a` (+ доки `60d9e16`) запушены — origin/main синхронен** (`fix(cli): UTF-8 stdout` — кириллица в Git Bash/пайпах + символ «≠» в warn-деталях не роняют печать; ревью `EXPERT_REVIEW_CLI_UTF8_OR.md`, GO с правками; 3 теста; **сервер не задет — cli сервером не импортируется, рестарт не требуется**). Состав коммитов: `src/spendtrack/doctor.py` + `tests/test_doctor.py` (25 тестов), правки `cli.py`/`main.py` (`GET /health/data`), доки PIPELINE/CONTEXT/continue.md. Ревью OpenRouter (`EXPERT_REVIEW_DOCTOR_OR.md`, $0, 337с): **GO с правками** — приняты `OR category IS NULL` для budgets (SQLite-квирк TEXT PRIMARY KEY; факт-проверено), detail quick_check (все строки ошибок), +5 тестов (db_open/taxonomy_config/precedence/NULL-budget/путь с пробелом); P0 про NULL в NOT NULL-колонках отклонены фактами (IntegrityError), кэш `/health/data` — YAGNI. Doctor: 9 проверок (quick_check/fingerprint_dupes/user_version/categories_invalid — critical; category_llm_invalid/refs_invalid/pending_source — warn; empty_batches — info; backup — info/warn/critical), CLI `uv run spendtrack doctor [--json]` (exit 1 только critical), API `GET /health/data` (503 при critical; `/health` не тронут). Живые смоуки: CLI на прод-БД (WARN только backup), dev-uvicorn `/health/data` 200 UTF-8 (остановлен). **Doctor нашёл и помог починить реальную проблему:** задача `spendtrack-backup` не срабатывала (LastTaskResult 0x800710E0; Principal Interactive + `DisallowStartIfOnBatteries=True` + `StartWhenAvailable=False`) — 16.09 17:58 включены догон пропусков, запуск на батарее, `ExecutionTimeLimit=PT1H` (XML-снимок до правки: `temp\spendtrack-backup.before.xml`); прогон задачи → `LastTaskResult=0` + свежий `spend-20260916-145810.db`, doctor = ok (см. `spec/PIPELINE.md` §Doctor). **Пуш и рестарт сделаны юзером 16.09 (вечер): origin/main = `1bd36bf`, live `/health/data` 200 `ok`.**
**Второе ревью** (другая модель, `EXPERT_REVIEW_DOCTOR2_OR.md`, $0): GO с правками — приняты `_guarded` ловит и `OSError`,
детерминированная сортировка бэкапов, +3 теста; попутно закрыт найденный нами пробел: **снимок 0 байт проходил
`quick_check` как пустая БД** → добавлена проверка наличия таблицы `transactions` в снимке. Отклонено фактами:
«утечка префикса fingerprint» (localhost; локальный злоумышленник читает саму БД), `MultipleInstances` (уже IgnoreNew),
NULL в `rules.category` (NOT NULL). **Правки doctor.py после ревью закоммичены `a20dcc8`** (+3 теста, 188 unit). **Инцидент 16.09:** 35 мин сессии шли на `hy4-preview` (клиентская смена модели в простое, без 429/автофолбэка; $0.80 = 86% стоимости сессии $0.93) — разбор в `MODEL_ROUTING_OPENCODE_GO.md` §12; там же 🔧 устаревшее окно off-peak в `go-usage.ps1` (наше 16:30–00:30 UTC vs офиц. пик 01:00–04:00/06:00–10:00 UTC пн–пт). Следующий deliverable: детекция рекуррингов/подписок (волна 1 п.2).** Ниже — исторические снимки; цифры в них не актуальны.
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
8. ✅ UI-блок закрыт: категории/правила/переименование (`c9c42c4`, `973d280`, `2e12d6c`) + бюджеты (`73cc5fa`).
   Далее: ① ✅ прод-NSSM перезапущен 16.09 13:08 (v4 + фикс дашборда; см. `spec/PIPELINE.md` — шаблоны Jinja
   применяются без рестарта, Python — только с рестартом: после правок и шаблонов, и кода сразу перезапускать);
   ② ✅ **реальная выписка — закрыто:** недоступна, контур синтетический (`D:\dev\docs\machine\TEST_DATA_STRATEGY.md`,
   DoD выполнен; property-тесты `parse_amount` добавлены 16.09); ③ ✅ smoke `/settings` пройден юзером (все чеки);
   ④ калибровка порога 0.9 — при решённых ≥20 (сейчас 2/20); ⑤ FinOps §11 / виртуализация — по триггеру;
   ⑥ ✅ CI e2e-джоб (`e5b13ac`); few-shot-фикс `approve-all` и сортировка очереди запушены (`35064ba`, `ce85a32`).
   ⑦ **Волна 1 (решение юзера 16.09) — ЗАКРЫТА (17.09, всё запушено):** ① ✅ **`doctor`/health целостности** (`0ad83f2`+`a20dcc8`,
   ревью ×3 + hardening `aa79fb9` — guard ловит любое исключение чека); ② ✅ **рекурринги/подписки** (`236525f`, ревью ×2;
   визуальный смоук выполнен агентом через playwright MCP — карточка «Подписки» на `/dashboard` найдена); ③ ✅ **`suggest-rules`**
   (`1b953c4`, ревью `EXPERT_REVIEW_SUGGEST_RULES_OR.md`, 14 unit). Калибровка 0.9 — по мере накопления решённых (2/20).
   ⑧ **Волна 2 — ЗАКРЫТА (18.09):** ✅ **дайджест недели + флаги аномалий** (`digest.py`, CLI `digest [--days N] [--json]`,
   карточка на `/dashboard`; 27 unit + e2e; ревью ×2 OpenRouter :free $0 — `EXPERT_REVIEW_DIGEST_OR.md`). Запушено.
   ⑨ **Волна 3 (пересобрана 19.09 по слепому аудиту Fable — `EXPERT_AUDIT_SPENDTRACKER_FABLE.md`):**
   ① **BYO-LLM/Ollama** (закрывает P0 «нет облака vs free-LLM»); ② **экспорт CSV/Excel**; ③ **one-command установка**
   (`uv tool`/uvx + bootstrap); ④ **лендинг + демо-кнопка** (Codespaces); ⑤ **PWA — только после 10 внешних пользователей
   с ≥2 импортами** (HTTPS/auth/телефоны — скрытая стоимость; ручной ввод нужен в основном для наличных).
   **Hosted убран из плана совсем** (ответ на запросы синка — экспорт/импорт + Syncthing/Tailscale).
   **Сделана фаза 0:** офлайн-first гейт LLM (без ключей — ноль сетевых вызовов), лимиты импорта (10 МБ / санитарные суммы),
   `PRIVACY.md`/`SECURITY.md`, тест «нулевой сети»; попутно найден и закрыт реальный баг: импорт не ставил `pending`/
   `category_llm` (низкоуверенные строки не попадали в очередь).
   **Осталось из аудита (S):** a11y-победы (`:focus-visible`, контраст, e2e-ассерты), golden-фикстуры через anonymizer,
   детектор дрейфа формата банка, «10-минутный сценарий установки» с 3 людьми, метрики-прокси (opt-in ping), offsite-бэкап.
   **Бэклог-опция:** парсеры банков отдельным MIT-пакетом (SEO/встраиваемость).

## Мета
- Возврат к работе: просто прочитай эти файлы: AGENTS.md (команды), CONTEXT.md (словарь),
  spec/ (детали), continue.md (статус).