# Continue.md — состояние проекта Spendtrack

Обновляется ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга: состояние живёт в файле,
а не в истории диалога). Здесь — только активный срез и последние сессии; полная посессионная история —
в приватном архиве `D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (сплит 24.09.2026 по методологии
progressive disclosure: `D:\dev\docs\machine\RULE_EXTRACTION_PLAN_received_2026-09-24.md`).

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx + Tailwind (offline-first ядро,
  LLM-шов только для остатка). Репозиторий: `D:\dev\personal\spend-tracker` (public,
  https://github.com/ExNihil14/spend-tracker). Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- Контур (30.09): **688 unit + 79 e2e + 40 cross-browser** + ruff (`check .`) + contract-дельта (осознанный
  snapshot 30.09 — аддитивный параметр `foreign_transactions_count`; при коммите нужен трейлер
  `Contract-Change:`) + ratchet (2/420) + cc + `build_css --check` (32 139 Б ≤ 35 КБ) — зелёные. Прод NSSM
  8766 — Running (200); демо-стенд 8799 жив; temp-стенд 8798 (проверочный, пустая БД) — в работе сессии.
- Последнее закоммичено: `6e3178f` (Wave 1-preview), `e270da4` (Wave 0), `4d41a83` (фикс-батч №2);
  в дереве — **Wave 1 лэйаут** (бенто/пилюли/постеры/count-up) + обновлённый `continue.md`. **push не делался —
  по команде юзера (main ahead origin).**
- Ребрендинг v2 «Стикербук»: направление принято (`D:\dev\docs\machine\DESIGN_DIRECTION_V2_2026-09-29.md`);
  Wave 0 + Wave 1-preview закоммичены, **Wave 1 (лэйаут) — в дереве**; 3D-графики отклонены (искажают значения).

## Что активно / в работе
> **АКТУАЛЬНО (30.09, день — дизайн v2 Wave 1 «Стикербук», лэйаут: ✅ в дереве, ждёт команды на коммит).**
> Внедрено без ожидания ревью Opus (ночное окно 02:00 UTC прошло до правки расписания задач; окно 11:00 UTC —
> ещё впереди, поллер стартует 13:57 local): nav — sticky-пилюли (`bg-accent-soft`+`aria-current`; фон шапки
> сплошной — `/95` давал «призрак» контента при скролле, поймано live-прогоном), `.chip-pop` счётчика очереди
> («поп» после htmx-свапа, spring; reduced-motion off); дашборд — KPI-бенто (`#kpi-balance` 2 колонки/`text-3xl`
> + спарклайн, tint-плитки дохода/расхода, переключатель месяца слим-строкой со `#dash-month`); постеры пустых
> состояний (лента/очередь/онбординг/пустой месяц, один на экран; CTA `bg-surface text-accent`); count-up целых
> процентов бюджета (`data-countup`/`-suffix`, после boost — `htmx:afterSwap`); `text-wrap: balance` заголовкам;
> `scroll-padding-top` под sticky. Контур: **680 unit + 79 e2e + 40 cross-browser** + ruff + contract + ratchet
> (2/420) + cc + build_css (32 139 Б ≤ 35 КБ) — зелёные. Live: демо-стенд 8799 (bento-ratio 2.05, count-up
> «143%…», sticky top=0, 0 ошибок консоли) + temp-стенд 8798 (пустая БД: постеры ленты/очереди) — скриншоты
> `C:\Users\HP\AppData\Local\Temp\opencode\wave1-live\`. Тесты: `tests/test_wave1_layout.py` (7) +
> `tests/e2e/test_wave1_layout_e2e.py` (5); контраст-пары градиента/постера в `test_tokens_contrast` (40 пар).
> Попутно: фикс ложного STOP секрет-скана `review.py` (SVG-path ловился как «карта») + по ревью Sonnet 5.5 —
> фикс пропуска карты с хвостовыми цифрами (TDD, 682 unit + ruff зелёные). **Пробное ревью Sonnet 5.5 через
> Abacus:** 30 с, ≈$0.20 — нашло реальный P1 в свежем коде (выше), $0-немотрон тот же диф пропустил (GO).
> Артефакты: `EXPERT_REVIEW_WAVE1_LAYOUT_{SONNET55_ABACUS,NEMOTRON3ULTRA}_2026-09-30.md`;
> `RESEARCH_SONNET55_REVIEW_TIER_2026-09-30.md` (решение по слою ②⁺ — за юзером).
> **Ещё два файловых ревью Sonnet 5.5 (Abacus, ≈$0.25 оба):** `store` — 4 принятых фикса с регресс-тестами
> (атомарная миграция + лечение частичного состояния, закрытие соединения при сбое init, guard «БД новее»
> с doctor-диагностикой, гонка дедупа → None), 1 отклонена фактом (соединение per-request), 2 отложены
> (TOCTOU approve-all, двойной коммит approve_review); `reports` — 2 фикса (ложный «скачок цены» двух
> параллельных подписок мерчанта; сноска валют зеркальна исключению transfers → **осознанный
> `contract_delta snapshot`**, baseline в careful-окне), 2 продуктовых решения за юзером (income/expense
> по знаку операции; знаковый daily-ряд). Артефакты: `EXPERT_REVIEW_{STORE,REPORTS}_SONNET55_ABACUS_2026-09-30.md`.
> AgentRouter: окно 02:00 UTC пропущено (расписание задач обновлено после его начала — задачи взведены:
> поллер Next 13:57 local); model-status 09:41 — opus operational 98.4%, astra degraded 97.2%. Push — по команде
> (spend-tracker ahead 1 + этот срез; bootstrap ahead 3).
> **АКТУАЛЬНО (30.09, утро — окна AgentRouter исправлены + консольный model-status).** Ночное окно 23:00 UTC
> пусто (60×402 — «Budget pool quota exhausted»). Официальный `/api/status` (announcement 28.08) задаёт
> релизы **Beijing 10:00/19:00 = 02:00/11:00 UTC**; консольный model-status (новый инструмент
> `agentrouter_status.py`, API `/api/user/model-status`, User-env `AGENTROUTER_ACCESS_TOKEN`+`AGENTROUTER_USER_ID`)
> подтвердил: claude-opus-5 «ok» в бакетах **02:00–03:20 UTC**. Поллер v8.1: окна (2,11) UTC, триггеры задач
> **04:57/13:57 local**, guard-фазы 01:55–05:00/10:55–14:00, model-status пишется в `batch.log`.
> Следующая попытка — **30.09 11:00 UTC (14:00 МСК)**, дизайн-ревью первым в очереди.
> **Закрытие сессии (30.09):** закоммичено `6e3178f` (Wave 1-preview — интерактив чартов/микро-моушен;
> **ahead origin 1**, push по команде); bootstrap — `f93bbcc` (guard: окна 02:00/11:00 UTC) + `c422f85`
> (`agentrouter_status.py`) — **ahead 3**. opencode перезапущен (pid 19916). Контур: 673 unit + 74 e2e +
> 40 cross-browser + ruff + contract + ratchet (2/420) + cc + build_css — зелёные; стенд 8799 и прод 8766 живы.
> **АКТУАЛЬНО (29.09, ночь — Wave 1-preview: интерактив чартов и микро-моушен. ✅ в дереве, не коммичено.**
> По запросу юзера («нет интерактивности/анимаций») до ревью Opus сделана безопасная часть Wave 1:
> Chart.js — тултипы в семантических токенах (фон `--fg-strong`, текст `--surface`, контраст ≥15:1; формат
> `−7 870,60 ₽` — U+2212/NBSP/запятая), hover-кромка баров (`--accent`), `hoverOffset` пончика, границы
> секторов по `--surface`, каскадное появление баров (delay 18 мс/индекс); **пончик интерактивен**: легенда —
> подсказка в шапке карточки («клик по категории — скрыть/показать; по сектору — список операций»),
> `cursor:pointer` над категорией и сектором, клик по категории — тоггл (скрыть/показать), клик по сектору →
> `/?category=…&month=…` (тот же фильтр, что у бейджей); count-up целых счётчиков (счётчик очереди,
> 3→4→6→8→9 проверено вживую; деньги НЕ анимируются) + «поп»; KPI-карточки `.lift` (hover-подъём,
> `(hover:hover)`, reduced-motion off); heat-cell hover; спарклайн — **мягкая сглаженная area-кривая**
> (монотонная кубическая интерполяция + градиентная заливка + мягкий вход; линия-«кардиограмма» и мини-бары
> отклонены юзером как невыразительные) от расхода дня.
> Контур: **673 unit + 73 e2e + 40 cross-browser** + ruff + contract + ratchet (2/420) + cc + build_css
> (30 389 Б ≤ 35 КБ) — зелёные; live на демо-стенде 8799 (0 ошибок в консоли; скриншоты
> `temp\opencode\wave1-*.png`). НЕ сделано (осознанно — после ревью): лэйаут (KPI-бенто, нав-пилюли,
> постеры пустых состояний), VT на стрелки месяца, 2.5D-tilt (Wave 2). 3D-графики — отклонены (искажают
> значения; «объёмность» дана градиентами/каскадом/hover).
> **АКТУАЛЬНО (29.09, вечер-3 — дизайн v2 «Стикербук», Wave 0: ✅ сделано (в дереве; ждёт команды на коммит).**
> Палитра: светлая «Аква-день» (canvas #f6f8fb, accent #0e7490, line-strong ≥3:1) / тёмная «Ночной стол»
> (canvas #0b1220, неон-аква #67e8f9); новые роли: `--accent-2` (ИИ), `--info`, soft-токены вместо alpha-чипов
> (`bg-warn-soft`/`bg-danger-soft`/`bg-accent-soft` — падавшие 3.56–4.34:1 закрыты), `--grad-*` + `.poster`
> (один градиентный бренд-момент, forced-colors-fallback), `--ease-spring`, радиусы 12/18/24, глобальный
> `:focus-visible`. Попутно: OOB-фрагменты `api.py` (счётчик очереди/импорт) переведены с захардкоженных
> amber/slate/red/blue на токены (tailwind-палитра ушла из app.css). Тесты: контрасты 37 пар × 2 темы
> (+14 новых из Приложения B), e2e-сигнал перекраски графиков переведён на цвет тиков (в v2 `--accent-bg`
> одинаков в темах). Контур: **673 unit + 72 e2e** + ruff + contract + ratchet (2/420) + cc + build_css
> (29 720 Б ≤ 35 КБ) — зелёные; живой прогон (temp-стенд 8799, demo-БД): light/dark + дашборд, computed-токены
> сверены (скриншоты — temp\opencode\wave0-*.png). Дальше: адъюдикация `out_design_review.md` (окно 23:00 UTC)
> → Wave 1 (нав-пилюли, KPI-бенто, постеры пустых состояний, микро-моушен).
> **АКТУАЛЬНО (29.09, вечер — фикс-батч №2, остаток: плагин C4/C2, адъюдикация bootstrap, tests_contour S2/S3/S6/S7). ✅ сделано (в дереве; ждёт команды на коммит).**
> Плагин: safety-gate v4 — `SAFETY_DATA_ROOTS` (default `d:/data`: write/read-тулы hard, shell — soft),
> careful-маркер **одноразовый**, журнал `metrics/safety-gate.jsonl` (arm/block/pass), hard-deny упоминания
> файла маркера; permission-ask на `*careful_gate.mjs*` (live+канон); тесты 6 сценариев/107 проверок, sync ок;
> **плагин подхватился живым сервером без рестарта** (факт: журнал live-сессии; правки opencode.json — рестарт).
> Bootstrap (адъюдикация `out_bootstrap_scripts.md`, все C/S + топ-5 закрыты — `ADJUDICATION_BOOTSTRAP_SCRIPTS_2026-09-29.md`):
> бэкап БД opencode → `D:\data\backups\opencode` + `last_backup.json` + каждые 4 ч (RPO), `restore-opencode-db.ps1`
> + drill (quick_check ok, 150 сессий) + `BACKUP_RESTORE_RUNBOOK.md`, offsite OneDrive (DB без credential),
> verify v3 (7 проверок: задачи/свежесть FAIL, offsite, канон), go-usage (S1-S3), check-channels (реальный ключ),
> start-detached, opencode-web, agent_context_audit (кириллица/`--project`).
> tests_contour: S2 (ratchet-guard на push в main), S3 (оффлайн-стаб ratchet-замера → 420), S6 (e2e-артефакты
> tracing + логи uvicorn в файлы), S7 (UPPER-константы в контракт-дельте; пп.1-2 закрыты 27.09).
> Baseline пере-снят (осознанно, юзер подтвердил): contract 49/304/32; ratchet 2/420.
> **Коммит-заметка:** изменение `spec/*_baseline.json` требует трейлера `Contract-Change: <причина>`.
> За юзером: команды на коммиты/push; pre-push hook + branch protection (agent_env C1) — решение.
> AgentRouter: окно 23:00 UTC (02:00 МСК) — дизайн-ревью первым; `out_install_ops/web_api/web_ui` — в очереди.
> **АКТУАЛЬНО (29.09, ребрендинг v2 «Стикербук» + фикс-батч №2): ✅ волны 1–9; два фикса закоммичены.**
> Дизайн: светлая тема по умолчанию + переключатель light→dark→system (localStorage `spendtrack-theme`, без FOUC),
> View Transitions, спарклайн/карта дней/градиентные бары, моушен с `prefers-reduced-motion`; a11y-гейты
> (axe A/AA × 5 страниц; кросс-движок chromium/firefox/webkit). Коммиты волн: `7d9bd0c`/`48a76d8` (1–4,6,
> запушены), `457dfde`/`21213c7`/`1102c37` (5,7,9). Спека:
> `D:\dev\docs\machine\DESIGN_DIRECTION_V2_2026-09-29.md` (белый лист + аква, категории-«стикеры», один
> градиентный постер на экран; 3D-графики отклонены — искажают данные) + `RESEARCH_REBRANDING_2026-09-29.md`.
> **Фикс-батч №2 (по ревью AgentRouter 29.09):** S5 `clean_state` — все таблицы, кроме `schema_migrations`
> (красный тест → зелёный, `0de1f61`); перекраска Chart.js при смене темы — событие `spendtrack:theme`
> (красный e2e → зелёный, `84967d1`). Остаток: плагинные C4/C2 (safety-gate: `SAFETY_DATA_ROOTS` для `D:\data`;
> `/careful` one-shot + журнал + ask), agent_env C1 (pre-push hook — решение юзера), C5 (свежесть бэкапов +
> offsite + drill), tests_contour S2/S3/S6/S7. Адъюдикация:
> `agentrouter_review\2026-09-27\ADJUDICATION_AGENT_ENV_TESTS_2026-09-29.md`; `out_bootstrap_scripts.md` —
> ждёт адъюдикации.
> **AgentRouter:** окна 23:00/11:00 UTC (02:00/14:00 МСК; поправка владельца 29.09); дизайн-ревью v2 для Opus —
> первым в очереди (`out_design_review.md`), попытка в 23:00 UTC.
> **АКТУАЛЬНО (27.09, вечер — README/Help/FAQ + визуальные ассеты): ✅ сделано (в дереве, ждёт команды).**
> README выровнен с приложением: импорт (drag&drop/файл/вставка), клавиатурный триаж очереди (j/k/Enter/s/1–9),
> подсказки правил (`spendtrack suggest-rules` — read-only), экспорт CSV кнопкой / Excel командой
> (`export --format xlsx`); FAQ +2 (клавиатура очереди; валютная сноска «не учтено N операций»); таблица команд
> (+`count`, `confirm <id> <категория>`, `suggest-rules`); «Разработка» — пересъёмка скриншотов.
> Скриншоты README пересняты с текущего UI (новый `scripts/record_readme_screens.py`: temp-копия demo-БД,
> guard на `demo.db`, 1280px); лендинг-GIF перезаписан (`record_demo_gif.py`); лендинг — точность формулировок
> (экспорт CSV кнопкой, подсказки правил командой). `/help`: исправлены неверные утверждения (категория правится
> только в очереди «Подтвердить»; удаления строк нет; демо-режим — для исходников/Codespaces; Excel — командой),
> +FAQ «Как разобрать очередь быстрее?», сноска про валюты, примеры категорий с RU-именами.
> Тесты: `tests/test_readme_screens.py` (ссылки README на картинки существуют; план съёмки == ссылки).
> Контур: **644 unit + 52 e2e** + ruff + contract + ratchet + build_css; live (temp-БД): `/help` и лендинг
> проверены Playwright. Релизный скилл: шаг «визуальные ассеты» + фикс нумерации. Дальше — команда на коммит.
> **АКТУАЛЬНО (27.09, вечер — адъюдикация батча Abacus «монетизация + процессы»): ✅ применено (ждёт команды на коммит).**
> Монетизация: C1–C4 + S1–S15 подтверждены — правки в 7 доках (`MONETIZATION_*`, `MNS_*`, `BUSINESS_PLAN`, `ANALYSIS`,
> `RESEARCH_BY_MARKETING_PROMO`): канон перков без «раннего доступа», возврат силами автора (Boosty не возвращает),
> gross-база чека ≈$18–19.5 чистыми, порог минимума ≈6 продаж (НПД выгоднее декларации от ≈5), эквайринг физлицу
> недоступен → ЕРИП/E-POS 1.2%, W4-proxy, письмо МНС Q1–Q7, «лицензия»→«услуги», день 0 = вторник.
> Процессы (bootstrap-остаток): read-hard-deny `.env`/маркера в safety-gate (+3 проверки, 69/69),
> `integrity_check` бэкапа + флоу «backup→update→check-opencode» в `check-opencode`, `ratchet_baseline` в protected.
> Артефакты: `agentrouter_review/2026-09-27/ADJUDICATION_{MONETIZATION,PROCESS}_ABACUS_2026-09-27.md`.
> Репо-правки этой сессии: только доки (`AGENTS.md`, `spec/TESTING.md` — lint `ruff check .` как в CI). За юзером:
> команды на коммит; решения монетизации (горизонт, mailto, kill-criteria, тестовые платежи); AgentRouter-пул —
> 8 ревью ждут окна 02:00 (иначе — решение: добить ключевые области Abacus-резервом или ждать).
> **АКТУАЛЬНО (27.09, ревью-гейты по Opus 5.5 — C4/C5/S1–S3/S7): ✅ закоммичено и запушено (`82728b8`).**
> `review.py`: дифф против `HEAD` (видит staged), пустой дифф → rc=2, пометка обрезок, расширения файлов,
> секрет-скан перед отправкой наружу (rc=3). `contract_delta.py`: индексы/триггеры/VIEW/`dflt` в schema,
> поля/декораторы классов и `__init__.py` в api, хэш операции в routes; baseline пере-снят (49/233/32).
> Новый `baseline_guard.py` + CI: изменение `spec/*_baseline.json` только с трейлером `Contract-Change:`
> (PR — `origin/<base_ref>`, push — `event.before`; `fetch-depth: 0`); `uv sync --locked --dev`.
> Контур: **642 unit + 52 e2e** + ruff + contract + ratchet + build_css. Окружение (bootstrap-коммит):
> safety-gate v3 (fail-closed, shell-protected, защита маркера), кап careful 15 мин, S4-фикс agentrouter,
> `check-opencode` v2 (бэкапы/канон/конфиг), ночной батч AgentRouter переведён на задачи Планировщика
> (mutex + guard, WakeToRun) — детали в плане/очереди.
> **АКТУАЛЬНО (27.09, тяжёлое ревью Opus 5.5 «деньги и целостность данных» через Abacus): ✅ сделано
> (`07598cf`, запушен).** Область — самый дорогой класс ошибок (тихие ошибки копеек/дедупа/валют);
> промпт по формуле claude.dev (одна задача + критерий «готово» + только merge-blocking + «как показать,
> что падает» + известные адъюдикации). Ревью (98 с, 50.5K in/9.5K out): 4 P1 → **3 приняты и исправлены**:
> ① Т-Банк — пара «Сумма платежа/Валюта платежа» (зарубеж по рублёвой карте больше не выпадает из ₽-итогов);
> ② календарная дата (`31.02`/`15.13` → `date_unrecognized`; раньше «добавлено, но невидимо во всех отчётах»);
> ③ незнакомая непустая валюта → `currency_unknown` (без молчаливой подмены на ₽). Отклонён фактом 1 P1
> (Сбер «Валюта счёта» — такой колонки в формате нет) + 2 «не подтверждено» (`get_store` — соединение
> на запрос; дата со временем отвергается API/CLI). Контур: **640 unit + 52 e2e** + ruff + contract +
> ratchet 2/435 + build_css; live temp-БД (CLI: −95000 ₽ / «1 пропущено (незнакомая валюта)» / «2 пропущено
> (нераспознанная дата)»); $0-ревью фиксов — GO. Артефакты: `EXPERT_REVIEW_MONEY_INTEGRITY_OPUS55_ABACUS_2026-09-27.md`,
> `EXPERT_REVIEW_OPUS55_FIXES_OSS_2026-09-27.md`.
> **АКТУАЛЬНО (27.09, §J-2 tail — CI-гейт базлайна + версии окружения): ✅ закоммичено и запушено (`3c52466`/`f039837`).**
> `ratchet.py`: ① подкоманда `guard --base origin/main` — рост гейтируемой метрики в базлайне PR против
> базовой ветки = FAIL (обход `snapshot --force` закрыт; осознанный рост — метка `ratchet-raise` в PR);
> CI-шаг «Ratchet baseline guard» (только `pull_request`, shallow-fetch base_ref); ② в снимок пишутся версии
> окружения (`env`: python/sqlite/platform), `check` при расхождении печатает WARN (не FAIL); реальный
> базлайн пере-снят (`snapshot` — env в файле, метрики те же 2/435). Live: guard против origin/main — ok;
> поднятая копия — rc=1 с подсказкой о метке; битая ссылка — rc=2. Контур: **638 unit + 52 e2e** + ruff +
> contract + ratchet + build_css. Остаток §J-2 (опционально): отвязать метрику от `tests/synth_bank.py`
> (зафиксированная фикстура-файл вместо импорта тест-хелпера). ✅ Ревью $0 (nemotron-3-ultra:free, 87 с):
> NO-GO → **обе находки (P0 «двойной compare» и P1 «str в current») отклонены фактами**: `compare()`
> вызывается один раз (стр. 282), `isinstance(current…)` в коде нет, при сбое `measure()` `current`
> остаётся `{}`; живой `check --json` — `failures: []` без дублей (`EXPERT_REVIEW_J2_TAIL_OSS_2026-09-27.md`).
> **АКТУАЛЬНО (27.09, §J-2 should — «контракт/формат/валюты/golden»): ✅ закоммичено и запушено (`1ebede4`…`e3edff4`).**
> ① `parse_amount`: адъюдикация фактами — контракт `InvalidOperation` уже ловится всеми швами (импорт →
> `amount_unparsed`, API → 422, CLI → exit 1); закрыто регресс-тестами (`nan`/`inf`/`1e400`/пусто/`abc`).
> ② `anonymize`: позиционная обработка `csv.reader/writer` — пустые/дублирующиеся заголовки, хвостовой `;`
> и поля сверх шапки сохраняются; опечатка в `--anon-column` → rc=1 без записи файла; `dst == src` запрещён;
> предупреждение о колонках без заголовка; `utf8_stdout` в `main`. ③ K6: зеркальный предикат
> `COALESCE(UPPER(currency), 'RUB')` в агрегатах и сноске (reports/digest/recurring/дневные итоги списка);
> `'rub'` = ₽; NULL невозможен (NOT NULL в схеме) — закреплено тестом. ④ `golden_report`: `utf-8-sig`,
> обязательные колонки, fail при пустом наборе/категории вне таксономии, якорь — сам репозиторий,
> `utf8_stdout`. ⑤ `backup.main` — `utf8_stdout` первой строкой. Live: anonymize-сценарии (хвостовой `;`/
> дубли/опечатка/перезапись) и K6 на temp-БД (сноска 1, расход −100,00); golden 34/34. Контур:
> **634 unit + 52 e2e** + ruff + contract (без дрейфа) + ratchet 2/435 + build_css. Остаток §J-2:
> CI-сравнение базлайна с `origin/main`, версии окружения в снимке. ✅ Ревью $0 (nemotron-3-ultra:free,
> 117 с): **NO-GO → 1 P0 принят и исправлен** — пустая строка валюты расходилась между SQL и Python
> (`NULLIF(currency, '')` выровнял, тест расширен); 4 находки отклонены фактами (CRLF сохраняется — тест
> `test_crlf_terminator_not_doubled`; cp1251-декодинг с `errors="replace"` не падает; `REPO_ROOT` — для
> документированного запуска из репо; поля сверх шапки round-trip'ятся) —
> `EXPERT_REVIEW_J2_SHOULD_OSS_2026-09-27.md`.
> **АКТУАЛЬНО (26.09, §J-2 critical — ложные гарантии гейтов): ✅ закоммичено и запушено (`f35c5db`/`522c416`).**
> `scripts/ratchet.py`: гейт больше не выключается молча — нет метрики/не число в базлайне или замере, битый
> или отсутствующий базлайн, неизвестная версия схемы и упавший `measure()` = FAIL в обоих режимах (было:
> `exit 0` в `--json` / `TypeError` в текстовом); порог «слишком хорошо» (0 или < 0.5×базлайна = FAIL);
> ассерты замера (seed 480 строк, отчёт 2026-06 непустой, импорт `ok`/104: 100 базовых строк + 4 фикстуры).
> `backup.py`: `--keep < 1` — отказ (rc=1) до создания снимка; offsite-копия **до** ротации; свежий снимок
> защищён и занимает слот `keep`; сортировка по `(mtime, name)` — критерий `doctor.check_backup`; `OSError`
> ротации (Windows: файл занят) — предупреждение, rc=0. Live-репро аудита: порча базлайна → exit 1
> (было 0/TypeError), мусорный импорт → `AssertionError` (было «улучшение» 435→2); temp-БД CLI — 4 сценария
> (keep 0/-1, копия-до-ротации, `--force`, залоченный файл). Контур: **619 unit + 52 e2e** + ruff + contract
> (snapshot: `rotate(*, current)` — осознанно) + ratchet 2/435 + build_css. Ревью $0 (nemotron-3-ultra:free,
> 215 с, $0) — **GO, блокирующих нет** (`D:\dev\docs\machine\EXPERT_REVIEW_J2_GATES_OSS_2026-09-26.md`);
> 4 «не подтверждено» проверены фактами (вне диффа/покрыто тестами; других вызовов `rotate` нет).
> Прод NSSM рестартнут (health 200, `/health/data` 13/13 ok). Остаток §J-2 (should): anonymize
> (усечение/PII/`dst==src`), контракт исключений `parse_amount`, K6 NULL/регистр валют, golden BOM/пути,
> CI-сравнение базлайна с `origin/main`, версии окружения в снимке.
> **АКТУАЛЬНО (26.09, аудит v2 на Opus-5 через AgentRouter).** Артефакты
> `EXPERT_AUDIT_V2_SRC_OPUS5_AGENTROUTER_2026-09-26.md` и `EXPERT_AUDIT_V2_SCRIPTS_OPUS5_AGENTROUTER_2026-09-26.md`
> (2+2 critical, 20+ should): бэкап `--keep 0`/ротация без OSError-защиты; ratchet-гейт молча выключается и
> «премирует» поломки; контракт `parse_amount`; `anonymize` (усечение/PII-опечатки/перезапись src); K6 NULL-валют.
> Пункты — очередь §J-2; применение отложено юзером — исправления делать следующим deliverable'ом.
> **АКТУАЛЬНО (26.09, гигиена секретов — закоммичено и запушено `f35c5db`).** Ключ Go-консоли перенесён из
> `<repo>\.opencode\go_key.txt` (файл был **не** в `.gitignore` и светился как untracked!) в User-env
> `OPENCODE_GO_KEY`; файл удалён; `.gitignore` дополнен `.opencode/*.txt` и `.opencode/*.key`.
> Проверено: `git check-ignore` ловит, `git status` без файла; `go-usage.ps1` работает (мес 48%, режим STOP).
> Инцидент-контекст — `D:\dev\docs\machine\OPENCODE_V2_INCIDENT_2026-09-26.md`; процедура ключа — bootstrap README.
> **АКТУАЛЬНО (25.09, §I M11 — contradiction-check публичных доков): ✅ сделано (в дереве, ждёт коммита).**
> `tests/test_docs_consistency.py` (7 оффлайн: цена/перки README↔лендинг, порог config↔лендинг, лицензия
> LICENSE↔README↔лендинг, банки `BANKS`↔README↔лендинг, выключенный FUNDING, совпадение install-URL);
> семантический промпт (Opus 5.5) и каденс — `spec/PIPELINE.md` §Contradiction-check (перед тегом K1 и раз
> в месяц; рекомендательный — тег не блокирует); шаг добавлен в скилл `release`. Контур: **605 unit + 52 e2e**
> + ruff; ревью $0 — все 5 находок приняты (`EXPERT_REVIEW_DOCS_CONSISTENCY_OSS_2026-09-25.md`).
> Остаток §I: S4/S5; далее Q6-остаток, K1 (юзер).
> **АКТУАЛЬНО (25.09, §I M10 — ratchet-метрики): ✅ сделано (в репо, ждёт коммита).** `scripts/ratchet.py`
> (temp-БД, прод не трогает): SQL-запросы на `report_month` = **2**, на импорт 100 строк = **435**
> (≈4.35/строку — кандидат в K7), медиана времени правил-категоризации — инфо (вне гейта). Baseline
> `spec/ratchet_baseline.json` — гейт «только вниз» (повышение лишь `snapshot --force`; путь в protected
> paths гейта), CI-шаг «Ratchet metrics» рядом с contract-дельтой; `tests/test_ratchet.py` (3).
> Контур: **598 unit + 52 e2e** + ruff + contract + build_css; ревью $0 — 1 P0+1 P1 приняты, 5 отклонены
> фактами (`EXPERT_REVIEW_RATCHET_OSS_2026-09-25.md`). Далее: §I M11 (contradiction-check), Q6-остаток, S4/S5.
> **АКТУАЛЬНО (25.09, §I M9 + Q6-каркас): ✅ M9 / 🔶 Q6 (dev-tooling, вне репо).** Плагин `skill-log.js`
> (канон bootstrap, копия в `~\.config\opencode\plugins\`; тест `skill_log_test.mjs` — 3 сценария/8 проверок,
> ревью $0 — 1 P1 принят, 6 отклонены фактами) пишет JSONL `D:\dev\docs\machine\metrics\skill-usage.jsonl`
> (ts/skill/session/cwd). `PROCESS_METRICS.md`: precision ревью **14/30 ≈ 47%**, rework **28/174 ≈ 16%**;
> «недотриггер» — из журнала после рестарта; стоимость/CI/уроки — ждут данных. Активация — рестарт opencode.
> **АКТУАЛЬНО (25.09, §I M8+Q5.2 — гейт деструктива/protected paths): ✅ сделано (dev-tooling, вне репо).**
> Плагин `safety-gate.js` (канон `D:\dev\bootstrap\config\plugins\`, копия в `~\.config\opencode\plugins\`):
> `.env`/`spec/contract_baseline.json`/`data/**` — hard-deny для edit/write/multiedit/patch; деструктив
> (force-push/`reset --hard`/`rm -rf`/NSSM remove/…) — только при свежем маркере careful-режима. `/careful`
> (команда + `scripts/careful_gate.mjs`, окно 10 мин); оффлайн-тест `safety_gate_test.mjs` — 4 сценария /
> 29 проверок (+sync канона); ревью $0 ×2 — 3 P0+1 P1 приняты, 2 P0+1 P1 отклонены фактами. Protected-actions —
> в `AGENTS.md` проекта (в дереве, ждёт команды на коммит). Активация гейта и триггеров скиллов — после рестарта opencode.
> **АКТУАЛЬНО (25.09, §I M7 — проектные скиллы): ✅ сделано (в дереве, ждёт коммита).** `.opencode/skills/`:
> `bank-adapter` (маршрут адаптер→фикстура→тест→golden + Gotchas реальных выписок), `release` (K1-контур:
> тег/CHANGELOG/пиннинг/заморозка/Windows-CI), `verify-spendtrack` (DoD-шаг live-прогона: сценарий из diff +
> 2 соседних потока, отчёт без правок). Регресс — `tests/test_skills.py` (7: name=каталог, description,
> Gotchas, живые указатели, авто-дискавери каталогов); указатели — AGENTS.md Layout + `spec/PIPELINE.md`.
> Контур: **595 unit + 52 e2e** + ruff + contract + build_css; ревью $0 (nemotron-3-ultra, 122 с) — 3 P1
> приняты, 2 P0 отклонены фактами (`EXPERT_REVIEW_M7_SKILLS_OSS_2026-09-25.md`). Канон = репо (opencode читает
> `.opencode/skills/` напрямую); срабатывание триггеров — после рестарта opencode. Коммит — по команде юзера.
> **АКТУАЛЬНО (25.09, Q2 — дедуп глобального AGENTS.md): ✅ сделан (dev-процесс, вне репо).** Глобальный
> `AGENTS.md`: 59 стр / ≈1 907 ток (было 86 / ≈3 412, −44%); факты → раздел «СРЕДА» `AGENT_ENVIRONMENT_PLAN.md`,
> роутинг-детали → `MODEL_ROUTING_OPENCODE_GO.md` §14; бэкап —
> `D:\dev\docs\machine\archive\AGENTS_global_2026-09-25_pre-Q2.md`; `agent_context_audit.py` — OK
> (28 указателей, 0 битых). Следующие deliverable: §I M7–M11 (Gotchas-скиллы, лог скиллов, ratchet-метрики,
> contradiction-check), Q5.2 (плагин-гейт protected paths), Q6 (`PROCESS_METRICS.md`), §I-S4/S5.
> AgentRouter-поллер: окно 22:55 UTC → результат в `C:\Users\HP\AppData\Local\Temp\opencode\agentrouter_review\`
> (проверить в начале следующей сессии).
> **АКТУАЛЬНО (25.09, АВАРИЙНЫЙ HANDOFF — сессия падает с 400):** `AI_APICallError: Bad Request`
> (opencode-go/deepseek-v4.1-flash). Факты: изображений нет, сессия переросла (514 сообщений, 4.6 МБ частей,
> компакции не было) → диагноз `D:\dev\docs\machine\OPENCODE_400_DIAGNOSIS_2026-09-25.md`; **дальше работать
> в НОВОЙ сессии по `D:\dev\docs\machine\SESSION_START_PROMPT.md`**. Git: `main` = **`2681a5f`**, ahead 6,
> дерево чистое. §G закрыт целиком (1–7, включая GIF `landing/assets/demo.gif`); §I-S1/S2/S3/S6 применены;
> **Q2 (дедуп глобального AGENTS.md) НЕ начат** — следующий deliverable (план в стартере); затем §I M7–M11,
> Q5.2, Q6 и K1 (тег/заморозка — за юзером). Контур: **588 unit + 52 e2e** + ruff/contract/build_css;
> прод NSSM актуален.
> **АКТУАЛЬНО (25.09, §G-1..3 — регресс-хардненинг):** property-based (`hypothesis`):
> `tests/test_property_parsers.py` (инвариант «любой ввод → запись или `_skip` с причиной; даты в БД только ISO»),
> `tests/test_import_chaos.py` (CR/CRLF/cp1251/битые байты, 20K-описание, лимит, пустышки, случайные байты,
> параллельная UI-запись), фикстуры миграций v3/v4. **Property-тесты нашли 2 реальных дефекта (закрыты):**
> csv падал на одиночном `\r` (нормализация переводов строк); `parse_amount("nan"/"inf")` → контролируемая
> `InvalidOperation` (CLI `add` — exit 1). Контур: **578 unit + 51 e2e** + ruff + contract + build_css;
> ревью $0 — 2 приняты / 8 отклонены фактами (`EXPERT_REVIEW_G_HARDENING_OSS_2026-09-25.md`);
> live: `add nan` → exit 1, CR-выгрузка → `+1 добавлено`. **Закоммичено `2c4c4ce`, прод рестартнут.**
> **§G-4/5 — ✅ закоммичено `33b5966`:** golden-набор `tests/golden/merchants.csv` + `scripts/golden_report.py`
> (read-only, `reports/golden.json`; база 34/34 rule-хитов, 6 нерешённых, 0 ошибок — основа калибровки 0.9),
> конкурентный HTTP-смоук (`test_concurrent_http.py`), e2e жизненного цикла категории. Контур:
> **581 unit + 52 e2e** + ruff + contract + build_css.
> **§G-6 (K6) — ✅ закоммичено `608952d` (+ `1ce6c4f` стабилизация концуррентного теста):** сноска
> «не учтено N операций в валюте» (`report_month`/`digest` + `foreign_transactions_count`; `/`, `/dashboard`,
> CLI `report`; показывается при N>0). Контур: **584 unit + 52 e2e**; ревью $0 — 0 принято / 2 отклонены
> фактами; live-факт на временном стенде.
> **§G-7 (K5-минимум) — ✅ закоммичено `2681a5f`:** GIF «импорт → подтвердить → дайджест»
> (`scripts/record_demo_gif.py`: изолированная копия demo-БД → временный uvicorn → 4 кадра Playwright →
> Pillow-подписи → `landing/assets/demo.gif`, 960px/~272 КБ) + `tests/test_demo_gif.py`, лид-кадр в `#screens`,
> README-ссылка; ревью $0 — 5 принято/2 отклонены (`EXPERT_REVIEW_GIF_DEMO_OSS_2026-09-25.md`).
> Контур: **588 unit + 52 e2e** + ruff + contract; live: лендинг 200, gif 200 `image/gif`.
> **§I (блог claude.dev) — инструкции применены:** `scripts/review.py` (только merge-blocking + «как показать,
> что падает» + неподтверждённое), `REVIEW_CHECKLIST.md`, глобальный `AGENTS.md` (итог «Нужно от тебя/Изменено/
> Найдено» + стоп-правило deliverable-скоупа), skill `research` (метки [П]/[Ч]/[?]). Осталось: §I-S4/S5, M7-M11.
> **АКТУАЛЬНО (24.09, K3 закрыт: публичные тексты + CHANGELOG):** README (браузеры/e2e-формулировка,
> `ruff check .` как в CI, EN/названия банков, NSSM-права, FAQ «Обновление/удаление», Docker-предупреждение,
> «Сайт»); лендинг (FAQ «импорт не распознал выписку» + `anonymize`; P1-6 — телеметрия vs `doctor --share`,
> free-opt-in в карточке LLM; минуты — drag&drop-шаг, caption Сбера, «≥ 0.9», Netflix → нейтрально,
> финальный CTA + macOS/Linux); **CHANGELOG `[0.2.0-beta]`** (Added/Changed/Fixed/Security + пометка
> историчности 0.1.0); **SECURITY** — приватный канал (PVR включён фактом), «localhost ≠ один пользователь»,
> BitLocker-заметка убрана; **PRIVACY** — free-цепочка generic; перки-канон выровнен (README/лендинг/
> `supporter.yml`). Первая часть закоммичена (`16f17a2`), K3-часть — в дереве, ждёт коммита.
> Контур: 561 unit + test_landing 11/11 + ruff + contract + build_css — зелёные.
> **АКТУАЛЬНО (24.09, dev-процесс: AI-native SDLC + контекст-аудит):** разобраны playbook Anthropic
> (`RESEARCH_AI_NATIVE_SDLC_PLAYBOOK_2026-09-24.md`) и RULE-EXTRACTION-план; внедрён
> `D:\dev\bootstrap\scripts\agent_context_audit.py` (бюджет/пороги/битые указатели/дубли); экспертиза
> arch-reviewer по открытым вопросам — решения в очереди §F; **посессионная история вынесена в приватный
> архив** (эта правка). Следующее: K3 (тексты + CHANGELOG) или K1 (контур; тег/заморозка — юзер).
> **АКТУАЛЬНО (24.09, сессия «K2-минимум — жизненный цикл данных»): ✅ `spendtrack backup` и `spendtrack anonymize`
> как CLI-команды пакета (deliverable; ждёт команды на коммит).** Логика перенесена из `scripts/` в
> `spendtrack/backup.py`/`spendtrack/anonymize.py` (скрипты — тонкие обёртки; у установок через uv tool их не было);
> `anonymize` — stderr-варнинг «даты/суммы/категории не обезличиваются» + `--rows` (дефолт 5, `0` — все;
> для dev-фикстур явно `--rows 0`); `backup` — прежние `--keep/--copy-to/--force` + суффикс при коллизии
> секунды; общий `console.utf8_stdout()` (stdout И stderr). Попутно закрыты реальные дефекты: CRLF-выписки
> (cp1251) при записи превращались в `\r\r\n` (text-mode Windows) — теперь bytes + регресс-тест; ошибки CLI
> («БД не найдена» и т.п.) унифицированы в stderr; отрицательный `--rows` и конфликт OUT/`-o` — явные ошибки.
> Тексты: README §«Обновление и удаление» (P1-4), единая формула пути к БД в README/PRIVACY/SECURITY +
> таблица команд и `/help` (P1-10, P1-3); прочие публичные хвосты (CHANGELOG/перки/лендинг-мелочи) — волна K3.
> Ревью $0 (gpt-oss:120b, 25 с): 3 приняты, 5 отклонены фактами —
> `EXPERT_REVIEW_K2_DATA_LIFECYCLE_OSS_2026-09-24.md`. Контур: **561 unit + 51 e2e** + ruff + contract
> (snapshot осознанно: +12 аддитивных символов) + build_css; live: temp-CLI (backup/guard/anonymize/обёртки) +
> прод NSSM рестартнут (health/health_data 200, doctor 13/13 OK, `/help` с новыми командами, свежий бэкап).
> Отложено тикетом: автобэкап перед миграцией + `backup --verify` (K2-остаток в RECOMMENDATIONS_APPLY_QUEUE).
> Следующее по очереди: K3 (тексты + CHANGELOG 0.2.0-beta) или K1 (Windows-CI/пиннинг; тег/заморозка — юзер).
> **Закоммичено `36bc0ea` (24.09); push — по команде юзера.**


## Архитектурные решения (frozen)
- Ключевые решения и список «не менять без ревью» — в `AGENTS.md` §«Ключевые решения» и `spec/ARCHITECTURE.md`
  (единственный источник; здесь не дублируем).

## Git-процесс
- Правила — `AGENTS.md` §«Git-процесс» (trunk-based, commit/push только по явной команде юзера); полный
  отчёт — `D:\dev\docs\machine\GIT_WORKFLOW_RECOMMENDATIONS.md`.
- Публичный репо, `main` защищён; история перезаписана 23.09 (`git-filter-repo`, старый e-mail вычищен).
- 24.09: посессионная история вынесена из публичного файла в приватный архив (указатель в шапке).

## Известные ограничения/грабли
- Правка юзера → merchant_cache + few-shot (правит будущий импорт).
- Не запускать qwen 7b одновременно с dev-сервером (GTX 1050 4GB).
- «Готово» без фактической проверки не принимается: diff/запуск/UI — факт, а не отчёт.
- Инженерные грабли и уроки — единый источник: `spec/PIPELINE.md`, `spec/TESTING.md`, `spec/ARCHITECTURE.md`.

## Возврат к работе
- Прочитай: `AGENTS.md` (команды/правила), `CONTEXT.md` (словарь), `spec/` (архитектура/контур), этот файл
  (статус + активный срез). Очередь применения — `D:\dev\docs\machine\RECOMMENDATIONS_APPLY_QUEUE_2026-09-24.md`
  (§F — процессные пункты из AI-native playbook и контекст-аудита). Фиксация сессии —
  `D:\dev\docs\machine\AGENT_ENVIRONMENT_PLAN.md` + Serena `spend-tracker/session-state`.
