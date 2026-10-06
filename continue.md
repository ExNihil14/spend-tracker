# Continue.md — состояние проекта Spendtrack

Обновляется ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга: состояние живёт в файле,
а не в истории диалога). Здесь — только активный срез и последние сессии; полная посессионная история —
в приватном архиве `D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (сплит 24.09.2026 по методологии
progressive disclosure: `D:\dev\docs\machine\RULE_EXTRACTION_PLAN_received_2026-09-24.md`).

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx + Tailwind (offline-first ядро,
  LLM-шов только для остатка). Репозиторий: `D:\dev\personal\spend-tracker` (public,
  https://github.com/ExNihil14/spend-tracker). Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- Контур (30.09, вечер): **723 unit + 86 e2e** + ruff (`check .`) + contract-дельта ok (осознанные snapshot'ы
  30.09; в коммитах трейлер `Contract-Change:`) + ratchet (2/420) + cc (do_import 12→11, baseline) +
  `build_css --check` (33 623 Б ≤ 35 КБ) — зелёные. Прод NSSM 8766 — Running (200); демо-стенд 8799 (200).
- Последнее закоммичено (30.09, вечер): `2bd8665` (фиксы дизайн-ревью), `da5c5ef` (фиксы install_ops,
  `Contract-Change:`), `bd2ae26` (continue), `63b24f1` (**фиксы web_api: F1–F8 + опционалы, `Contract-Change:`**),
  `b2a7e25` (continue) — **всё запушено, origin/main = `b2a7e25` (ahead 0)**.
  **Сервисы перезапущены на новом коде:** прод NSSM 8766 (health 200), демо-стенд 8799 (health 200, 349 tx +
  пробная tx id=350 «LIVE PROBE» pending — data/** protected, не чищу).
> **Dash «второй голос» (30.09→01.10, эксперимент):** Dash (Process Street) подключён как MCP к opencode
> (89 тулзов, `tools.dash.*`; баланс $199.69 = 40k старт + 40k за GitHub). Два headless-ревью (Opus 4.6 / 4.8,
> skill `code-review`, read-only) по свежим коммитам; 4.8 прогнал тесты (723 passed). Находки и вердикты:
> `D:\dev\docs\machine\DASH_CODE_REVIEW_2026-10-01.md`. **Фиксы ждут команды (TDD):** ① рассинхрон лимита суммы
> API ±10^15 коп vs CSV-импорт 10^11 коп (главный улов); ② dashboard.js фолбэки #7c8ba1→#6f7d94; ③ backup.py
> unlink-гард; ④ store.py rename→replace; ⑤ тест порога disk_space. Бэклог: e2e-ниты, лимит тела POST, HX-413.
- Ребрендинг v2 «Стикербук»: направление принято (`D:\dev\docs\machine\DESIGN_DIRECTION_V2_2026-09-29.md`);
  Wave 0 + Wave 1-preview + **Wave 1 лэйаут (`a89f42f`)** закоммичены; 3D-графики отклонены (искажают значения).

## Что активно / в работе
> **📦 ВОЛНА 1 wave5 (Astra ночь 06.10) — СДЕЛАНА 06.10 (TDD, в дереве, ждёт коммита).**
> `anonymize`: C3 (guard «выход≠источник» и для авто-имени — симлинк-тест), C1 (оценка кандидатов
> шапки + отказ при ничьей), C2 (непустой лист без шапки → отказ; одноколоночные с известной шапкой),
> should-4/5 (комментарии/гиперссылки со всех ячеек; свойства книги — новый `DocumentProperties`),
> 6-lite (формула → отказ). `settings` C1: бюджеты/ошибки НЕ публикуют `#tax-hash`; конфликт не
> выдаёт новый токен; e2e бюджета переписан (токен меняет только taxonomy-мутация). `core`: №1
> (export пустой/NULL-валюты сохранённой строки → «RUB»), №3 (лимит взносов `MAX_AMOUNT_KOPECKS` +
> CHECK, **schema v8** + миграция пересборкой; строки сверх лимита → явный отказ), №4 (SQLITE_BUSY/
> LOCKED → 503; прочие `OperationalError` → 500+трейсбек), №6 (`_DATE_RE` fullmatch + ASCII).
> `core_ops` (1b): lazy-бэкап без своей ротации; re-check свежести под lock; `isfinite` +
> отсев future-mtime; doctor-сводка «недоступно» вместо чужой БД. Bootstrap 1c (`ops_bak`):
> раздельная ротация полных/неполных; устойчивый `serena_lost` (`serena_expected`, rc=2,
> `.incomplete`, `--forget-serena`); ошибка маркера → rc≠0 и ротация после публикации; атомарный
> DB-маркер (`.part`→`replace`). **Контур: 903 unit + 98 e2e** + ruff + contract ok (осознанный
> snapshot: `SCHEMA_VERSION 8`; schema=76 / api=386 / routes=38) + ratchet + cc + build_css —
> зелёные; bootstrap-тесты `backup_*` — ALL PASS. **Live:** прод NSSM 8766 и демо 8799
> перезапущены (обе БД на v8, `/health/data` ok, demo.db подтверждён), CLI `anonymize` на temp.
> **Ревью $0** (nemotron-3.5-lightning:free): NO-GO → **5×P0 отклонены фактами** — разбор в
> `D:\dev\docs\machine\agentrouter_review\2026-09-27\ADJUDICATION_WAVE5_2026-10-04.md` §«Волна 1»
> (артефакт `D:\dev\docs\machine\EXPERT_REVIEW_WAVE5_1_OR.md`). Коммит/push — по команде юзера.
> **Остаток:** Волна 2 — goals S1–S9 (S3/S4/S5/S6 — дизайн-обсуждение), anon-7, core №5
> (атомарный кэш валюты + снимок базы на операцию), ops_bak 5–8 (возраст артефакта в verify,
> missing-ветка, MCP-политика, `Get-FileHash`), ui_srv optional (двухвкладочный e2e); Волна 3 —
> core №7 (docker-smoke), goals O1 (журнал архива), UUID правил. Окно 11:00 UTC 06.10 (14:00 local):
> pending 2 (`site_ui`, `ops_srv`), watcher'ы армлены.
> **АКТУАЛЬНО (03.10, вечер — копилки Ф0 в дереве, ждёт коммита).** Schema **v7**: `goals` + append-only
> `goal_allocations` (STRICT+CHECK, FK RESTRICT; миграция аддитивная, v6-БД апгрейдится при старте) +
> Store CRUD (`add_goal`/`list_goals`/`archive_goal`/`add_allocation`/`list_allocations`/`goal_progress`) +
> 6 тестов (Python-валидация + SQL-второй рубеж). Контур: 802 unit + 93 e2e + ruff + contract ok
> (snapshot schema 76 / api 348) + ratchet + cc (HX-413 вынесен в helper — без роста do_import) + css.
> Сервисы уже перезапущены на этом коде: прод 8766 и демо 8799 — 200; обе БД на **v7** (spend.db и demo.db,
> миграция со снимком). Урок: `doctor` открывает Store и **мигрирует БД** — если прод-код в памяти ещё старый
> (v6), запросы падают 500 «БД новее приложения»: после snapshot'а схемы рестартить сервисы сразу. Грабли:
> 8799 стартует только с `SPENDTRACK_DB_PATH=data/demo.db` — без него молча
> поднимается на прод-БД (записано в скилл `verify-spendtrack`). Также 03.10 закоммичены:
> `4164789` (TOCTOU), `bb38e71`+`641b3a4` (Dash-бэклог), `7e0938a`+`3b15bbc`+`5d6d2eb` (копилки Ф0 + helper + доки).
> **README актуализирован (03.10, ждёт коммита):** hero-GIF наверху, новый скрин очереди `/approve`, фичи
> (редактор правил/категорий, тёмная тема), статус «бета» (как на лендинге), `backup --drill` в таблице;
> ассеты пересняты на свежем демо-сиде v7 (4 PNG + лендинг-GIF), план съёмки расширен. Дальше — **Ф1 прогресс (UI/CLI)**.
> **Беларусь/BYN (03.10, prep):** ресёрч `D:\dev\docs\machine\RESEARCH_BELARUS_BYN_2026-10-03.md` (банки BY:
> машиночитаемый экспорт подтверждён только у Белагропромбанка `.xls/.doc` [П, факт-чек PDF]; BYN ISO-4217
> совместим с копейками; NBRB API; таксономия BY; интеграционный план: `base_currency`-настройка + SQL-параметризация,
> схема не меняется). **Банк юзера — Приорбанк** (03.10, точечная доразведка §2.3): розница не подтверждена,
> но бизнес-интернет-банк отдаёт выписку в **CSV/TXT/DOCX/PDF** [П]; план проверки — приложение/web/заказ документов.
> Адаптеры — **data-gated** (нужен обезличенный образец от юзера). $0-ревью **выполнено** (`out_belarus_review_or.md`,
> nemotron-ultra:free) и **адъюдицировано** (`ADJUDICATION_BELARUS_REVIEW_2026-10-03.md`): Ф0 ready, Ф1 data-gated
> (образец Приорбанка; нет ~2 нед → закрыть), BY-правила — opt-in overlay, `.xls` без `xlrd` в core, PDF не раньше Ф3.
> Тикет — в §7 стартера. Практический гид «как переключить локацию» — `GUIDE_LOCATION_BELARUS_BYN_2026-10-03.md`.
> **AgentRouter wave5 (04.10): 11/17 готово** (пул 402 после `ops1`; хвост ops2+Astra — следующее окно).
> Адъюдикация — `agentrouter_review/2026-09-27/ADJUDICATION_WAVE5_2026-10-04.md`. Улов: **живой critical
> 500** (`v.items` в `goals_list.html` — Jinja-коллизия; падала страница целей и фрагмент ПОСЛЕ коммита) —
> починен сразу с регресс-тестом; **волна 1 фиксов в дереве** (fingerprint base-независим, periods+1,
> пустые валюты→RUB-фолбэк, кэш без отравления, даты/TOCTOU, taxonomy health/education+fallback,
> `#goals-error`-слот, disabled-elt, портфель-горизонт, pending-бейдж). **Волна 2 (anonymize+ops) —
> сделана:** предупреждения анонимайзера (нулевое обезличивание, PII вне таблицы, `.xlsm`-отказ,
> свойства книги), doctor-краш, lazy_backup-контракт; bootstrap: CRIT-1/2 (`.part`-публикация, staging
> в try/finally) + msvcrt/all-empty. **Волна 3 (тесты/UX) — сделана:** goals S1/S2/S4/S6/S10/S11 +
> e2e-локаторы карточек, feed S4/S6, settings-контракт, ui_js S1–S3/S6, store-доки v6. **Волна 6
> («wave6-хвосты») — сделана:** feed S1/S2 (свап только `#tx-table` + OOB `#tx-actions`) и S3
> («+ валюта» у смешанного дня), anonymize S3/S4/S5 (фантомный `max_row`, merge/фильтр, роутинг по
> магии), settings №5, ops_spend №5/№6 (serve-порядок, CI docker-smoke), ops1 SHOULD-3/4
> (`secure_delete`+VACUUM, атомарный маркер), Docker PATH. **Волна 6+ (settings №2/№6) — сделана:**
> `#tax-hash` вне root + OOB-хэш каждой мутации + подстановка на запрос (app.js) → свежесть без свапа
> root; бюджеты — свап своей строки, иконка — строки, цвет — `swap=none` + тост. Контур
> **863 unit + 96 e2e**, bootstrap-тесты ALL PASS, snapshot api=383. **Волна 6++ (ops1 SHOULD-1 +**
> **store S4) — сделана:** деградация не отключает ротацию (пол 2×keep, рост ограничен; +5 проверок
> bootstrap); `_migrate_v6` не читает отсутствующие колонки (схемы «created без updated» и «без обеих»
> мигрируют; +2 теста). **Волна 6+++ (ops1 OPT) — сделана:** `<root>` в walk-ошибках, тесты (сбой
> testzip, walk_errors, локальный credential сохраняет, happy-ротация), неполный архив —
> `.incomplete.zip`. Контур **865 unit + 96 e2e**, bootstrap-тесты ALL PASS. Остаток: хвост окна
> (ops2+Astra). Коммит — по команде.
> **Ресёрч «обработка ошибок» (04.10, фоновый субагент):** `D:\dev\docs\machine\RESEARCH_ERROR_HANDLING_2026-10-04.md`
> (327 строк, 15 первоисточников, метки [П]/[Ч]). Топ-разрывы: htmx не показывает не-2xx (нет `htmx:responseError`;
> молчат create 422/413, reviews 404/409), нет глобального `exception_handler` (500 = plain-text, HX тихо стоит),
> `OperationalError` (busy >5 c) → 500 без текста, строки/коды ошибок рассыпаны (нет реестра под `t()`), a11y:
> импорт/создание в `role=status`, нет `aria-invalid`. Сильные стороны: миграции/дедуп-гонка/approve-транзакции/
> LLM-цепочка с breaker — не трогать. **Предложение волн:** W1 — htmx-ошибки видимы + глобальный handler(Exception)
> + OperationalError→503 + битый taxonomy на `/settings` + serve-TOML (все S, TDD); W2 — `errors.py`-реестр строк/кодов,
> таблица CLI-кодов, a11y ошибок (alert/aria-invalid), `llm-status`: last_error, DEBUG-PII-правило. Ждёт команды.
> Проверить вручную (§5 дока): сумма `abc` в UI, битый CSV, повторный approve, занятая БД >5 c, битый taxonomy,
> `serve` с битым settings, NVDA на ошибках.
> **W1 ресёрча ошибок — сделана (04.10, в дереве):** htmx-ошибки видимы (#error-banner role=alert +
> `htmx:responseError/sendError`), глобальные handler'ы 500/503 (JSON для HX/API, HTML для браузера; лог без
> query/тела), `OperationalError`→503 (в тесте — реальная занятая БД), битый taxonomy.toml → баннер /settings
> (и в мутациях), serve/CLI при битом TOML/занятой БД → rc=1 без трейсбека. TDD: 9 красных → зелёные;
> контур **874 unit + 97 e2e**. W2 (реестр строк/кодов под `t()`, CLI-таблица, a11y alert/aria-invalid,
> `llm-status`: last_error) — по команде.
> **W2 ресёрча ошибок — сделана (04.10, в дереве):** `errors.py` — реестр кодов/строк (500/503, суммы,
> «не число») с тестом-связкой; ошибки импорта (HX) — `role="alert"`; `add` при дубле — отдельный код **4**
> (штатный no-op; таблица кодов — `spec/PIPELINE.md`); `llm-status` показывает `breaker` и последний сбой
> (тип+время, без тел); `CircuitBreaker.state()`; правило «DEBUG-логи только локально» — в REVIEW_CHECKLIST
> и комментарии categorize. Контур **880 unit + 97 e2e**; contract: api **386** (snapshot в дереве —
> коммит с трейлером `Contract-Change: api=386`).
> **a11y-хвост ресёрча ошибок — закрыт (04.10, в дереве):** 422 помечает ошибочные поля `aria-invalid`
> (+рамка danger), фокус уходит на первое ошибочное поле, правка поля снимает пометку (e2e проверяет
> все три шага). **Ресёрч «обработка ошибок» исполнен полностью: W1 + W2 + a11y.** Контур 880 + 97.
> **Ресёрч Habr «free-сервисы + важные статьи» (04.10, фоновый субагент):**
> `D:\dev\docs\machine\RESEARCH_HABR_FREE_SERVICES_2026-10-04.md` (183 строки; валидность — по офиц. страницам).
> Живое: OpenRouter :free (20/мин, 50/день → 1000 при ≥$10), Render Free (демо-кандидат), Neon/Supabase/Turso,
> UptimeRobot, Tailscale Funnel, Actions/Codespaces. Мёртвое/платное: FreeLLMAPI, Roo Code, Fly.io/Koyeb (free нет).
> Статьи-рецепты: idempotency+SW-outbox (волна 3), WAL-Reset (наш SQLite 3.53.1 — фикс есть), FastAPI+SQLite
> прод-стек, gitleaks/секреты, htmx 4.0 (не мигрировать до stable). **Адъюдикация:** по команде берём — S:
> `integrity_check` в restore_drill, аудит toggle→set-state, pre-commit gitleaks, правило «.env не читать»;
> отложено — PWA/idempotency (волна 3), демо Render+UptimeRobot+GoatCounter (роадмап), кандидаты в free-цепочку
> (Gemini free учится на данных — выписки нельзя); вручную за юзером — secret scanning+push protection,
> лимиты Groq/Mistral/Together, видимость порта Codespaces.
> **Habr-адъюдикация исполнена (04.10, в дереве):** pre-commit gitleaks — установлен и **провалидирован вживую**
> (staged-секрет блокирует коммит; найдена ловушка upstream-хука: без `pass_filenames: false` gitleaks молча
> пропускает); правило «`.env` не читать» — в AGENTS.md; `integrity_check` в restore_drill и toggle→set-state —
> **отклонены фактами** (integrity_check уже стоит; toggle-роутов нет — всё set-state). **Блок 2 — результаты (04.10):**
> GitHub secret scanning+push protection — ✅ ON, алертов нет; Groq — ✗ 403 (браузер и сеть); Mistral — ✗ Free без API
> («Upgrade to use your API keys»); Together — ✗ ключ deprecated + мин. платёж (⚠️ ключ засветился в чате — **отозвать**);
> Cohere/Cerebras — 403 с сети (браузером: Cohere 403 и в браузере; Cerebras — Cloudflare-бот-блок) → не закладываться.
> Кандидатов в free-цепочку нет — остаётся OpenRouter :free + локальные шимы. **Блок 2 закрыт полностью:**
> Codespaces 8766 = Private ✓.
> **Иконка темы (04.10, в дереве):** тоггл показывает ДЕЙСТВИЕ (светлая → луна, тёмная → солнце), title —
> «Переключить на … тему»; e2e обновлён (rebrand 13 passed), CSS пересобран (34 003 Б). Рестарт не требуется
> (шаблоны/статика), коммит — по команде.
> **Сессия 04.10 закрыта:** `origin/main = c355e30` (push выполнен 22:16); bootstrap: `.pre-commit-config.yaml` —
> коммит `8e7a3d2` (запушен 22:27); сервисы 200/200; guard жив (хвост окна: **ops2 ✅ 05.10 02:06** (ждёт адъюдикации); **7 Astra** — WAF-блок Alibaba (405) с 02:08, следующее окно 11:00 UTC = 14:00 local; поллер пропатчен: WAF-backoff 15→30→60 мин + точный парсинг кодов + skip sensitive_words; preflight v2 OK, pending 7).
> Хендофф новой сессии: `C:\Users\HP\AppData\Local\Temp\opencode\HANDOFF_2026-10-04_spendtracker.md`;
> стартер обновлён: `D:\dev\docs\machine\SESSION_START_PROMPT.md`.
> **CI-инцидент закрыт (05.10, ~00:00): ✅ исправлено и запушено** (`3513a86` fix(deps) + `d46336b` fix(ui);
> origin/main = `d46336b`). CI прогон **37234190816 — зелёный** (все 5 джобов: lint-and-test, e2e, cross-browser,
> docker-smoke, secret-scan; ранее скипавшиеся шаги contract/ratchet прошли). Причины были: urllib3 2.7.0
> (PYSEC-2026-4175/76/77), +1px reflow на `/dashboard` при 320px (числа KPI), webkit-канвас +159px после resize.
> Прод NSSM и демо 8799 перезапущены (200/200; живой чек 320px/resize = 0 overflow). Урок: сверять `gh run list`
> перед «зелёно» (локальный контур ≠ CI).

> **Сессия 05.10 (утро) закрыта:** `origin/main = d46336b` (CI зелёный), `M continue.md` (эти заметки — коммит по
> команде); bootstrap: `origin/main = 9c31847`, **ahead 1** (`f3871fc`, волна ops2-3) — push по команде.
> **AgentRouter:** ночное окно — `ops2` ✅ (адъюдицирован полностью: волны ops2-1/2/3); Astra 0/7 — WAF-блок
> Alibaba (405) + sensitive_words (site_ui 2/2; словарного триггера нет); поллер v8.2 (WAF-backoff 15→30→60 мин,
> точный парсинг кодов, per-run skip) + guard v3 (проба только в окне, таймаут, cap 3); pending 7, preflight OK;
> **следующее окно 11:00 UTC 05.10 = 14:00 local**. **Прочее:** sensitive-ревью исполнено; S-волна контент-анализов
> → PLAYBOOKS (ledger §E); Shemsedinov 6 видео/83 записи (+шортсы 119; `T90` — не дубль qA); `-Sfib` — 429.
> **PR #6** (dependabot setup-uv) — open. Go — STOP (месяц 89%). Хендофф:
> `C:\Users\HP\AppData\Local\Temp\opencode\HANDOFF_2026-10-05_spendtracker.md`; стартер обновлён
> (`SESSION_START_PROMPT.md`, 05.10 утро).
> **Сессия 05.10 (вечер) закрыта:** окно 11:00 UTC — Astra отдала 1 вывод: **`site_tail` ✅** (адъюдицирован:
> GO; **5 правок приняты и в дереве**, каждая red→green: приватность логов — ASCII-канарейка + percent-encoded;
> `test_repo_hygiene` — структурный YAML по активным узлам; `llm.py` — `_err_lock`/`_mark_error` (+ монотонность
> last_error, снимок под локом); `install-gitleaks.ps1` — сравнение PATH по элементу; e2e
> `test_poster_cta_reachable_by_keyboard` — Tab-цикл вместо хардкода 40). Далее WAF держал окно до ~12:2x UTC
> (разбор/уроки — `agentrouter_review/2026-09-27/ANALYSIS_WAF_2026-10-05.md`), **пул закрылся 12:19 (402)** →
> окно исчерпано; **7 Astra остаются в pending**. **Поллер усилен:** v8.4 (Opus-fallback: 18 под-заданий по
> `FB_PLAN`, 15 fb-сплитов ≤37 КБ, `check_fb_splits.py` — 0 пропусков/0 лишних), v8.4.3 (канарейка: status
> 403/405 → проход без заданий), **v8.4.4 (402 = сон до дедлайна без запросов)**; оффлайн-тесты
> `test_run_fallback.py` 7/7; watcher-канон `watch_window.ps1` (вычисляемое окно, выход по `pool_closed`).
> Поллер остановлен вручную 16:05 (после 402 «пинговал» впустую), **guard возвращён** авто-задачей (17:05;
> одноразовая задача удалена). **Грабля демо-запуска:** `$env:SPENDTRACK_DB_PATH` в `-Command` start-detached
> раскрывался вызывающей оболочкой → стенд молча поднимался на ПРОД-БД; правильный вызов (одинарные кавычки
> через переменную) и проверка свежего `detach-*.ps1` — предупреждение в шапке `start-detached.ps1`.
> **Контур: 884 unit + 98 e2e + ruff + contract ok + ratchet + cc + build_css — зелёные**; прод 8766 и демо
> 8799 (demo.db подтверждён `/api/budgets`) — 200/200 на коде дерева. **Abacus (190 кр):** анализ
> `ANALYSIS_ABACUS_REVIEW_BUDGET_2026-10-05.md` (варианты A/B/C — решение за юзером). **Открыто:** коммит
> (9 файлов spend + bootstrap `agentrouter_chat.py`/`start-detached.ps1`), push `b224358`/`f3871fc`,
> site_ui решение (Astra: скип/в конец), канонизация `continue.md` (WARN аудита), выписка Приорбанка.
> Следующее окно — **02:00 UTC 06.10** (05:00 local); стартер обновлён (`SESSION_START_PROMPT.md`, 05.10 вечер).
> **Ночь 06.10 (окно 02:00 UTC) — итог + адъюдикация:** Astra отдала **6 из 8** частей (site_ui_srv,
> site_core, site_core_ops, site_goals, site_anon, ops_bak; exit=0, 3.8–6.7 мин каждый). `site_ui` —
> sensitive_words **4/4** (per-run skip); `ops_srv` — пул закрылся в 03:18 UTC → **v8.4.4-сон без запросов**
> отработал; канарейка (403/405) и WAF-backoff тоже подтверждены живьём. Pending — **2** (`site_ui`, `ops_srv`).
> **Адъюдикация: 6×NO-GO** (статическое кросс-семейное ревью; critical структурно подтверждены):
> ① `site_ui_srv` — протокол `#tax-hash` (бюджетные/ошибочные ответы публикуют свежий хэш при устаревшем DOM →
> удаление «не того» правила в двух вкладках); ② `site_anon` — 3 critical (шапка по титульной строке; непустой
> лист без шапки сохраняется; **регрессия** — guard «выход≠источник» потерян для автоимени → симлинк
> перезаписывает исходник); ③ `ops_bak` — 2 critical (ротация считает `.incomplete` и может снести полные
> копии; `serena_lost` забывается после прогона); ④ `site_core` — export исторических строк в текущей базе;
> нет лимита суммы у взносов (overflow → ложный 503); `OperationalError` целиком → 503; ⑤ `site_core_ops` —
> lazy-бэкап (чужая ротация / TOCTOU / future-mtime / inf-nan); ⑥ `site_goals` — 9 should (движок времени,
> портфель, what-if, формы). Полный разбор + план волн — `ADJUDICATION_WAVE5_2026-10-04.md` (§Astra ночь 06.10).
> **Дальше — Волна 1 (TDD red→fix):** anon C1/C2/C3 + should 4/5/6-lite; ui_srv C1 (протокол + e2e);
> core №1/№3/№4/№6; core_ops 1–3 + optional; ops_bak critical 1/2 + should 3/4. Watcher'ы переармлены на
> 11:00 UTC (14:00 local; `watch_window.ps1` v2 — сам целится в следующее окно; `watch_window_events.ps1`).
> Открыто: push (spend **ahead 5**, bootstrap **ahead 1**), site_ui-skip, Abacus A/B/C, канонизация continue.md.
> Стартер обновлён (`SESSION_START_PROMPT.md`, 06.10 — волна 1).
> **Анализ DeepSeek Harness (04.10):** `D:\dev\docs\machine\ANALYSIS_DEEPSEEK_HARNESS_2026-10-04.md` — вывод:
> как замена opencode не нужен; точечно — проба на локальной Ollama (30 мин, нулевой бюджет, изолированный
> workspace) для GUI/XLSX-кейсов; идеи (GitHub-review-сессии, reminders, плагины) — в бэклог. НЕ внедряем сейчас.
> **BYN-prep: `anonymize` под XLSX сделан (03.10, в дереве, ждёт коммита):** `anonymize_xlsx` (openpyxl,
> in-place: шапка в первых 10 строках, псевдонимы сквозные, строки за `--rows` удаляются), CLI-роутинг по
> расширению/магии ZIP, legacy `.xls` — понятная ошибка «сконвертируйте в .xlsx/CSV» (NO-GO без xlrd);
> +5 unit (test_anonymize); README/skill/ресёрч обновлены. Ф1 всё ещё data-gated (образец Приорбанка).
> **Ф0 «базовая валюта» сделан (03.10, в дереве, ждёт коммита):** настройка `base_currency` (settings/env,
> ISO-валидация, default RUB) + SQL-параметризация агрегатов (reports/digest/store/recurring/frontend/export/cli) +
> символы `fmt_money`/`currency_symbol` (₽/Br, иначе код; JS дашборда — через `data-currency-symbol`) + doctor-чек
> `base_currency` + импорт/CLI/API по умолчанию пишут базовую + fingerprint по базе (код только для НЕ-базовой).
> +8 тестов; контур **810 unit + 93 e2e** + ruff + contract ok (snapshot api 352) + ratchet + cc + css; live:
> BYN-режим на прод-БД (read-only) — doctor OK («вне итогов: 8»), отчёт 0.00 + сноска «не учтено 8».
> Дальше — коммит по команде; Ф1 ждёт образец Приорбанка.
> **Копилки Ф1 (прогресс UI/CLI) сделан (03.10, в дереве, ждёт коммита):** страница `/goals` (+ nav «Цели»),
> htmx-формы создания/взноса/архива, прогресс-бар с aria, журнал взносов, пустое состояние; API `/api/goals*`;
> CLI `goal list/add/allocate/archive` (+`--json`) + строка целей в `digest`; README/help. +8 unit (test_goals_ui)
> + 2 e2e; контур **818 unit + 95 e2e** + ruff + contract snapshot api 363/routes 38; live на демо 8799:
> цель создана, взнос 2500 → 25% (страница+фрагмент). Дальше — **Ф2 движок** (capacity/required/статусы).
> **Копилки Ф2 (движок) сделан (03.10, в дереве, ждёт коммита):** `goals.py` — capacity (медиана net за 6 полных
> месяцев, покрытие «конец месяца ИЛИ ≥5 операций»), «слабый месяц» = min, `required = ceil(need/периоды)`,
> pace = медиана взносов; статусы DONE/ON_TRACK/AHEAD/BEHIND/AT_RISK/OVERDUE/NO_DEADLINE/INSUFFICIENT_DATA/
> NO_CAPACITY_DATA (нейтральные ярлыки); шаблонные советы what-if (singles→пары ≤40%, только
> `discretionary`-категории из taxonomy, рекурринги исключены); предупреждения (история/очередь/валюта/регулярки);
> портфельное предупреждение «метки > потока»; UI: статус/«чтобы успеть»/варианты/предупреждения на `/goals`;
> CLI `goal list` + digest-строка со статусом. +11 unit (test_goals_engine) + digest-тест; контур **830 unit +
> 95 e2e** + ruff + contract snapshot api 381 + ratchet + cc (goal_engine/what_if разбиты на хелперы ≤10) + css.
> Live (8799): «Демо-цель 25% [без срока]». Дальше — Ф3 LLM (LATER) / по сигналу.
> **АКТУАЛЬНО (02.10, окно 11:00 UTC — 5/5 ✅; адъюдикация + фиксы, коммит по команде).** Окно закрыто 12:46 UTC:
> js_a/js_b (Opus), templates_a/b (Opus, со 2–3-й попытки), bootstrap_scripts_astra (Astra). Вердикты:
> js_b NO-GO (карта дней считала знаковый total_k → расходы нулями, aria-label врала) — фикс + e2e; templates_a
> C1: meta htmx-config стояла ПОСЛЕ htmx.min.js (allowEval/historyCacheSize не применялись) — фикс + rename-cancel
> в app.js + e2e; templates_b GO: настройки без id теряли фокус (id+role=alert+aria-label), file_hash протухает
> при частичном свопе (волна 2: #settings-root); bootstrap C1: OAuth-токены попадали в OneDrive ДО strip
> (фикс: strip локально → .part → публикация; rc=2 при провале копии; пустая БД = BAD; тест-скрипт ALL PASS).
> Ещё фиксы: approve.js S1/S3/O3 (getTbody/делегирование, фильтр afterSwap, change-диспатч), app.js S2, theme.js O1,
> dashboard.js S1/S2/S3/S8; фильтры `hx-swap=outerHTML` (дубль #tx-table), `/help#` hx-boost=false, #importmsg/#newmsg
> role=status, FX-дни «только в валюте», urlencode категорий, careful_gate O3 + тест, README setx→Read-Host.
> **Контур: 772 unit + 91 e2e + ruff + contract ok + ratchet 2/420 + cc + css — зелёные; прод 8766 и демо 8799
> перезапущены, live: allowEval=false, один #tx-table, heat 6 ненулевых ячеек («всего 20 600,00 ₽»),
> 16 budget-id / 18 color-id / 32 rule-id.** **Коммиты:** `983d9fe`+`1be4a92` (spend-tracker),
> `0716e0e`+`0c74acb`+`97d2291` (bootstrap). **Волна B:** settings S2 (`#settings-root` — свежий file_hash) ✅,
> tx_card (шапка+«месяц» в фильтрах) ✅, noscript ✅, js_b S7 закрыт фактом; контур 774+93;
> bootstrap: S1/S2/S3 (backup-knowledge `.part`→testzip, `serena_lost`, rc=2 при провале копии + тест ALL PASS) ✅,
> S11 (start-detached: WorkDir pre-check → rc=3) ✅; S4/S6–S10 (verify/check-channels/go-usage/opencode-web +
> тесты ALL PASS) ✅, канон `opencode.json` синхронизирован (MCP→V2 `servers`); suggestion-гард ✅;
> контур 775+93; остаток: O1 ✅ (region-lock `.backup.lock`), O5 закрыт фактом (бюджет едет за rename),
> O6 оставлено осознанно (root-свап сбрасывает превью), O11 частично (aria «Открыть»/«Приоритет», catname).
> **03.10 (окно 11:00 UTC):** wave4 → 402 «pool quota exhausted» в 12:16 — выходов 0 (окно потеряно).
> **Разбор процесса:** `agentrouter_review\2026-09-27\ANALYSIS_BATCH_PROCESS_2026-10-03.md` — Opus-таймауты
> 36% на 38–50 КБ (thinking 20–24K); Astra 7/7 ok на 60–96 КБ. **Политика v2:** Opus-часть ≤35 КБ / thinking 12K
> (сплит >40), Astra — монолиты, таймауты с деградацией/переносом, preflight-гейт (`--dry-run`, `--pending`),
> guard стартует при pending>0. **Очередь пересобрана: 7 джобов** (`p1/p2/p3`, `ops1/ops2`, astra site/ops),
> preflight OK; поллер на новой очереди с 12:55 UTC (пробы до 14:00; иначе — окно 02:00 UTC).
> **Ресерч «копилки/цели» (03.10):** `D:\dev\docs\machine\RESEARCH_SAVINGS_GOALS_2026-10-03.md` (75 КБ,
> 24×[П]). Вердикты: расширяемо «виртуальным конвертом» (goal + append-only allocations, schema v6,
> без привязки к балансам, которых у нас нет); советы — «числа считает код, LLM только формулирует»
> (whitelist чисел + офлайн-шаблоны + opt-in шов); ревью Opus 5.5 оправдано, промпт готов (§9;
> каналы: Abacus / Zen ~$0.32 / окно AgentRouter $0). Решение по тикету schema v6 — за юзером.
> **Ревью выполнено** (Abacus `claude-opus-5-5`, 96 с, `out_goals_review_abacus.md`): NO-GO fixable —
> STRICT/CHECK для v6, валюта неизменяема при аллокациях, id/created_at/idempotency, «полный месяц»
> по покрытию импорта, **LLM: плейсхолдеры вместо whitelist**. Адъюдикация с факт-чеком —
> `ADJUDICATION_GOALS_REVIEW_2026-10-03.md`; MVP: Ф0 schema+CRUD → Ф1 прогресс → Ф2 subset (LLM — LATER).

> **Тикет C2 закрыт (03.10, TDD):** `spendtrack backup --drill` — снимок + проверка восстановимости;
> `config.resolve_db_path()` — единая точка пути к БД (без legacy ROOT и cwd-зависимостей; переведены
> drill/backup/doctor); дрилл перенесён в пакет (`scripts/restore_drill.py` — шим). Контур: 779 unit + 93 e2e,
> contract snapshot (api 318→325; коммит — с трейлером `Contract-Change:`), live: `backup --drill` → ok (count/sum match).
> **Тикет C3 закрыт (03.10, TDD):** ленивый бэкап на старте `serve` — `backup.lazy_backup_if_stale()`
> (порог `SPENDTRACK_LAZY_BACKUP_HOURS`, дефолт 168 ч, 0 — выключить; lock/ротация/никогда не бросает);
> `cmd_serve` сообщает о созданном снимке, сбой — warning. +5 тестов; контур 784 unit + 93 e2e;
> contract snapshot (api 327); live на temp-БД: created → fresh. Следующий шаг очереди — S1 (settings-merge).
> **Тикет S1 закрыт (03.10, TDD):** `load_settings` — merge «пакетные дефолты ← пользовательский TOML»
> (+ терпимость к BOM от Windows-редакторов); `doctor`: новый чек `settings_config` (critical вместо крэша),
> `build_usage_summary` не падает при битом конфиге; `paths_info` печатает раскладку без Settings. +4 теста;
> контур 788 unit + 93 e2e; contract snapshot (api 328); live: неполный+BOM settings.toml → merge (port/db/llm).
> Следующий шаг очереди — CI-smoke установки (docker build+run+doctor).
> **Тикет CI-smoke установки закрыт (03.10):** `.github/workflows/ci.yml` — джоб `docker-smoke`
> (build → run fresh volume → health → doctor/paths → cleanup, actions запинены, timeout 20 мин).
> Локальный прогон-доказательство: образ собрался, health 200, `doctor: OK` (15 чеков, включая
> `settings_config`), `paths` — installed-раскладка /data; SMOKE OK.
> **Тикет get_one-whitelist закрыт (03.10, TDD):** `GET /api/transactions/{id}` — `response_model=TxOut`
> (публичный whitelist: без fingerprint/account_anon/export_rowid/import_batch); +тест «ровно эти поля»;
> контур 789 unit + 93 e2e; contract snapshot (api 328→341, components обновлены).
> **Тикет CHECK(date)-миграция закрыт (03.10, TDD):** schema **v6** — `CHECK(date GLOB 'YYYY-MM-DD')` на
> `transactions` (щит слоя данных); легаси-апгрейд — пересборка таблицы (пересечение колонок, backfill NULL
> created/updated); мусорные даты блокируют миграцию явной ошибкой (pre-migration-снимок рядом). +3 теста
> (fresh-мусор / апгрейд v4→v6 / блокировка); контур 792 unit + 93 e2e; copy-check на копии прод-БД:
> 8/8 строк, CHECK ok; live: прод и демо — на v6, `doctor: OK`, count 8/8. Contract snapshot (schema v6).
> Следующий шаг очереди — двойной коммит approve_review / TOCTOU approve-all (или Dash-бэклог).
> **Тикет TOCTOU/двойной коммит закрыт (03.10, TDD):** `approve_all_reviews` — `BEGIN IMMEDIATE` вокруг
> SELECT..UPDATE + откат всего пакета при сбое (P1-5); `approve_review` — UPDATE + few-shot-кэш **одной
> транзакцией** (P1-7): сбой seed откатывает approve; публичные сигнатуры без изменений. +2 теста;
> контур 794 unit + 93 e2e. Следующий шаг — Dash-бэклог (e2e-ниты, лимит тела POST, HX-413).
> **Dash-бэклог закрыт (03.10, TDD):** `POST /api/transactions` — лимит JSON-тела `MAX_JSON_BYTES`=64 КБ
> (413 до парсинга); `/api/import` — переразмерный JSON для htmx отдаёт дружелюбный фрагмент (HX-413);
> e2e-ниты — вместо `wait_for_timeout(250)` детерминированное ожидание (URL месяца + Chart), вместо
> tab-loop 40 — прямой `focus()` CTA. +2 unit-теста; контур 796 unit + 93 e2e; contract snapshot (api 342).
> **Очередь тикетов пуста.** Дальше — продуктовые решения: копилки (research 03.10; schema будет v7 —
> v6 занята CHECK(date)) или слой ②⁺ (Abacus/Zen).
> **АКТУАЛЬНО (01.10, вечер — адъюдикация Astra×5, волна 1 ✅ в коммите `c9f75c6`).** Окно 11:00 UTC дало
> Astra-проход (5/6: install_ops / llm_seam / tests_contour a+b / agent_env; `bootstrap_scripts_astra` —
> пустой ответ → `bad/`, повтор в следующем окне). Артефакт адъюдикации:
> `D:\dev\docs\machine\agentrouter_review\2026-09-27\ADJUDICATION_ASTRA_2026-10-01.md` (~60 находок,
> вердикты + план волн). **Волна 1 (TDD, +19 тестов):** `review.py` — STOP при чувствительных tracked-путях
> (утечка выписок/PII наружу!), `-z`-разбор (не-ASCII имена), `prompt_sha256`; `categorize/taxonomy` —
> валидация типов ответа LLM + OverflowError + кэш-income не применяется к расходу; `llm.py` — `parse_llm_json`
> без regex-обхода массива, пустой HTTP-200 = сбой (fallback/breaker), `llm_status` — origin без секретов;
> `ratchet` — NaN/`{}` больше не выключают гейт; `contract_delta` — SQL таблиц (CHECK/UNIQUE/FK) + components
> OpenAPI (осознанный snapshot, `Contract-Change`); `install.ps1` — `$LASTEXITCODE`; `config.py` — env > TOML.
> Контур: **747 unit + 86 e2e** + ruff + contract ok (schema 58 / api 313 / routes 34) + ratchet 2/420 +
> cc + build_css — зелёные. **Волна 2 ✅ (`b9f4cb1`):** изоляция снимков по БД (`backup/<stem>/`) + lock
> (C1/S2 install_ops), doctor-warn без бэкапов для непустой БД (ЛГ-2), restore_drill пути+схема (S8/S9),
> fail-closed провайдеров + loopback-диапазон (C4/S14), авто-приём LLM не учит кэш (C3), системные
> категории защищены (C5); контур **757 unit + 86 e2e** + все гейты — зелёные, contract snapshot (api 318).
> **Волна 3 ✅ частично (`cc2db69` + safety-gate v5):** llm_seam S4–S8/S12/S13 (merchant доходит до LLM,
> account/date убраны — egress; few-shot через `json.dumps` и фильтр по таксономии; pending сохраняет исходный
> merchant; HTTP-клиент закрывается; ключ по точному origin); **safety-gate v5** (bootstrap, вне репо):
> `git -C/-c …` и `reset … --hard` больше не обходят правила, write-API python в `data/` виден эвристике,
> тесты `safety_gate_test.mjs` — ALL SCENARIOS PASS. Контур **764 unit + 86 e2e** + все гейты — зелёные.
> **Волна 3 (остаток):** llm_seam C6 (rename-атомарность), S16–S22; tests S4/S5/S6/O2/O3;
> agent_env S2–S5 (SSE-разделители, FIFO, Retry-After, origin ключа в agentrouter-ua.js);
> install_ops S1/S3/S5/S7 (README-комплект, runbook, Git-зависимость, пути/paths_info).
> **АКТУАЛЬНО (01.10, утро — фиксы Dash-ревью 4.6/4.8, ✅ в дереве, ждут команды на коммит).** По
> `D:\dev\docs\machine\DASH_CODE_REVIEW_2026-10-01.md`, TDD (красный → фикс → зелёный):
> ① API-лимит суммы сведён к общей константе `MAX_AMOUNT_KOPECKS` (10^11 коп = 1 млрд ₽; было ±10^15 —
> «5 млрд ₽ принимается API, но молча отбрасывается CSV»); ② dashboard.js фолбэки `#7c8ba1`→`#6f7d94` ×2;
> ③ `backup.make_snapshot` — unlink частичного файла в try/except OSError (не маскирует исходную ошибку);
> ④ `store._pre_migration_snapshot` — `replace` вместо `rename` (Windows rename не перезаписывает);
> ⑤ тест порога `disk_space` (мок `shutil.disk_usage`, граница `max(1 ГБ, 3×размер БД)`).
> Контур: **727 unit + 86 e2e** + ruff + contract ok (без дрейфа) + ratchet 2/420 + cc + build_css (33 623 Б) —
> зелёные. Live: temp-стенд 8798 — 5 млрд ₽ → 422 («сумма сверх лимита на операцию (до 1 000 000 000,00 ₽)»),
> граница ±1 млрд ₽ → 200, +1 коп → 422; прод NSSM 8766 и демо 8799 перезапущены на новом коде (health 200,
> dashboard 200). Бэклог Dash: e2e `sleep(250)`/tab-loop, лимит тела POST, текст даты, HX-413, `-wal`
> в `disk_space`, `_did_exist`→локальная. Полные тексты ревью — `DASH_REVIEW_FULLTEXTS_2026-10-01.md`
> (пункт 7 Boom принят 01.10: `__getattr__`).
> **Окно AgentRouter 02:00 UTC (01.10) не состоялось** (ночью ПК был выключен/в сне — завершение сеанса
> 00:59 local; догон-запуск поллера 07:18 UTC → «too early for window 11:00»); новых `out_*` нет; следующая
> попытка — **сегодня 11:00 UTC (13:57 local)**: `web_ui_js` → `web_ui_templates` → Astra×5 (бюджет ≈65–70 мин).
> **Окно AgentRouter 11:00 UTC (30.09) — итог:** старт 11:00:15 UTC (триггер 13:57:57 local), model-status в логе;
> `out_design_review.md` ✅ (447 с), `out_install_ops.md` ✅ (366 с), `out_web_api.md` ✅ (~18 мин — расщеплённое
> досье влезло), `out_web_ui.md` — **срезан закрытием пула в 12:10 UTC** (наш http-таймаут 12:10:07, ретрай —
> 402; клиентский потолок 12:11:37 не успел). **Урок: реальный бюджет окна ≈65–70 мин генерации** (11:00:15→12:10,
> сходится с 28.09), Astra-проходы не стартовали — «добирают» остаток следующих окон. **`web_ui` расщеплён** по
> уроку `web_api`: `prompt_web_ui_templates.md` (75 КБ) + `prompt_web_ui_js.md` (37 КБ, дополнен `theme.js`),
> очередь поллера обновлена (dry-run ок) — в окне **01.10 02:00 UTC** стартуют обе половины (~45–50 мин), затем
> Astra. Running-поллер (в памяти — старая очередь) до 14:00 UTC лишь ретраит 402 каждые 180 с и само-выйдет.
> **Адъюдикация дизайн-ревью — `ADJUDICATION_DESIGN_REVIEW_2026-09-30.md`:** исправлено C1 (белое кольцо фокуса
> на постере — transition-colors учитывать при проверке), C3 (`--line-strong`: light `#6f7d94`, dark `#6d7fa3`,
> +4 контраст-пары, канон §3.3/§3.4/§3.6 обновлён), C2-guard (`nav` static при высоте <500px), S3 (`@media print`
> для постера), S7 (инвариант моушена уточнён в каноне); гейты S4 (1.4.12 text-spacing) и S6 (таргеты ≥24) —
> e2e; C4-guard (семантические alpha-фоны в шаблонах запрещены тестом). C6 отклонён фактом (destroy на
> `htmx:beforeSwap` уже есть) + регресс-тест на утечку инстансов; C5 отклонён по премиссе (LLM — реальный шов).
> Тикеты: rendered-composite контраст-тест, S1/S5, слепые зоны (forced-colors/prefers-contrast/VT-focus).
> **Адъюдикация install_ops — `ADJUDICATION_INSTALL_OPS_2026-09-30.md`:** pre-migration-снимок перед миграцией
> (C1; тест), offsite-маркер `forced` → doctor WARN (S5; тест), unlink частичного VACUUM INTO + чек `disk_space`
> в doctor (S6; тесты), README (C2-runbook с `-wal`/`-shm`, C3-планировщик бэкапа, S2-команда обновления,
> S4-docker, S7-логи, S8-стоп автозапуска). Тикеты: `backup --drill` (C2-остаток), lazy-backup на старте serve (C3),
> merge settings (S1), `resolve_db_path` (S3), CI-smoke установки.
> **Адъюдикация web_api — `ADJUDICATION_WEB_API_2026-09-30.md` (внедрена, закоммичена `63b24f1`):** F1 нормализация даты
> (`20260912`→`2026-09-12`, live ✓), F2 400 на не-объектный JSON, F3 cap ±10^15 коп (OverflowError подтверждён),
> F4 коррекция снимает с очереди (роутер-уровень, store.py не тронут), F5 лог generic-сбоев импорта, F6 blank-поля
> форм, F7 троттлинг `?fresh=1` 2с + ключ кэша doctor + lock, F8 max_length (contract-snapshot осознанно);
> опционалы: pending_count(), seed после 404, OOB-бейдж в create-HX, дедуп бейджа, MultiPartException→ImportLimitError
> (+`form.close()`), `_setup_logging`→lifespan, эхо input≤200, локальная дата бюджета (api+cli). Отсрочено:
> get_one-whitelist, CHECK(date)-миграция. Грабля: starlette 0.27 `_get_form` конвертирует MultiPartException в
> СВОЙ HTTPException(400) — родитель fastapi-шного, `except fastapi.HTTPException` не ловит.
> **web_ui/Astra — адъюдикация после окна 01.10 02:00 UTC.** Контур: **723 unit + 86 e2e** + ruff + contract ok +
> ratchet 2/420 + cc (12→11, baseline update) + build_css (33 623 Б). Сервисы 8766/8799 перезапущены (health 200;
> в demo.db пробная tx id=350 «LIVE PROBE» pending — не чищу, data/** protected).
> Флак axe (замер посреди каскада строк) закрыт детерминированно: перед axe доигрываем
> CSS-анимации (`document.getAnimations().finish()`).
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
> **Wave 1.3–1.4 (30.09, по запросу юзера):** тема — **кнопка-тоггл светлая↔тёмная** (как на opencode.ai),
> иконка меняется CSS по `[data-theme]`, `aria-pressed`; `system` убран (легаси → светлая); FOUC-гард.
> **Иконки категорий:** внешний спрайт `static/cat-icons.svg` (32 symbol ≈9 КБ) + глобал `cat_icon`
> (цепочка явное `icon` → слаг → `tag`; кэш по mtime; SPENDTRACK_TAXONOMY учитывается); **банк +14 иконок
> для кастомных категорий** + в настройках колонка «Иконка» (селект/автосохранение) и выбор при создании
> (роут `POST /settings/categories/icon`). **«Расходы»:** стикер-аватары (38% + наклон −4°, hover-выпрямление),
> дни-таймлайн (пилюля+линия+итог), каскад появления ≤7×18 мс, **конфетти** на пустой очереди (одноразово,
> aria-hidden, MutationObserver-тест) + 🎉; попутно исправлен невалидный OOB-DOM пустой очереди (обёртка
> `<tbody>` — htmx вставляет детей oob-элемента). Осознанный snapshot контракта (api 311/routes 33).
> Контур **775** + gates зелёные; live на 8799 (после рестарта Python — правило!): пикер 32 иконки/19 селектов,
> 59 стикер-аватаров, тоггл, 0 ошибок консоли; скриншоты `temp\opencode\sonnet-reviews\wave14-*.png`.
> Дальняя «температура» — `D:\dev\docs\machine\DESIGN_PLAYFUL_TEMPERATURE_2026-09-30.md`.
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
