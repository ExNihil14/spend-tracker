# CONTEXT.md — словарь домена Spendtrack

Короткий словарь для агентов. Используй эти термины вместо перифразов.

## Термины
- **Транзакция** — одна операция (доход/расход) из банка или CLI. Поля: date, description, amount_kopecks (INTEGER копеек), category, category_source, confidence, merchant, account_anon, import_batch, fingerprint, category_llm, review_status.
- **Сумма** — всегда `amount_kopecks` INTEGER (копейки). −12345 = −123.45₽. НИКОГДА не REAL.
  `parse_amount(str) → int` (принимает `,`/`.` и типографские минусы); `fmt_amount(int) → "-123.45"`
  (машинная ASCII-форма: CSV/промпты/CLI); `fmt_amount_signed(int) → "−123.45"/"+123.45"` (знак-форма);
  **UI-форма — `fmt_money(int, currency='RUB', signed=True) → "−155 365,18 ₽"`** (NBSP-разряды, десятичная
  запятая, ₽ или код валюты; `signed=False` — лимиты/бюджеты без «+»); `fmt_month('2026-09') → "Сентябрь 2026"`;
  `fmt_date('2026-09-13') → "13.09"` (таблицы; ISO остаётся в экспорте/API). U+2212 — WCAG 1.4.1
  (цвет не единственный носитель смысла).
- **Валюта** — `transactions.currency` (ISO 4217, `NOT NULL DEFAULT 'RUB'`, миграция v5). `normalize_currency()`
  понимает «₽/руб./rub/$/€/доллар»; незнакомое значение в импорте → RUB, в API/CLI (`add --currency`) — ошибка.
  Не-RUB **не участвует в ₽-агрегациях** (отчёты, бюджеты, дайджест, рекурринги, дневные итоги) и не склеивается
  дедупом с ₽-аналогом (fingerprint включает код только для не-RUB). В UI код показывается рядом с суммой,
  в экспорте — колонка «Валюта»; агрегаты не молчат о выпавших операциях — сноска «не учтено N операций
  в валюте» (K6) в итогах/дайджесте/CLI (`foreign_transactions_count`).
- **Бейдж категории / контраст** — цветной бейдж с названием; цвет текста подбирает `colors.badge_text_color(bg)`
  (#020617 или #ffffff по контрасту, ≥4.5:1 для всех дефолтных цветов taxonomy; тест `tests/test_colors.py`).
- **Категория** — одна из 18 в `config/taxonomy.toml` (groceries, restaurants, transport, fuel, housing, utilities,
  internet-phone, subscriptions, health, education, entertainment, clothing, household, transfers, income, taxes,
  travel, other). У каждой — `display_name` (RU-имя для UI); слаг остаётся ключом в БД/URL/API, в интерфейсе
  рендерится `catname(slug)` (неизвестный слаг — как есть).
- **Источник категории** (`category_source`) — как получена: `rule` (keyword-правило), `llm` (принято от LLM, conf≥0.9), `llm_pending_review` (низкая уверенность → в очередь), `import` (из CSV банка), `manual` (создано вручную), `correction` (правка юзера).
- **Подтверждение (review queue)** — транзакции с `review_status='pending'` (ставится при `category_source='llm_pending_review'` — LLM дал conf<0.9 или категорию вне таксономии). `category_llm` — предложение LLM (не перезаписывается → рендер-diff). `approve` → `category`=выбранная + `category_source='rule'`; `skip` → вне очереди, категория не меняется; `approve-all` → `category=COALESCE(category_llm, category, 'other')`, с `min_confidence` (0..1) — только записи не ниже порога (UI: ≥60% — безопасный bulk, M-4).
- **Мерчант** — нормализованное имя (UPPER). `merchant_cache` → связанная категория (выигрывает над правилами/LLM).
- **Fingerprint** = sha1(date|kopecks|norm(desc)|account_anon|export_rowid). Дедуп импорта: повторный импорт = no-op. norm = UPPER + collapse пробелов.
- **Партия импорта (import_batch)** — один загруженный CSV, id `b_hex`, sha256 содержимого, статус.
- **Дрейф формата / отчёт импорта** — перед разбором проверяются обязательные колонки банка (`REQUIRED_COLUMNS`,
  синонимы с допуском пробелов/регистра; включают реальные шапки: Сбер email-CSV «Дата совершения операции»/
  «Сумма в валюте счета», Т-Банк 13 колонок с MCC — `RESEARCH_BANK_STATEMENT_SAMPLES.md`). Смена формата →
  `status="format_error"` (`missing_columns` — группы синонимов через « / », `found_columns` + `message`
  с просьбой прислать обезличенный образец), БД не трогается. Отчёт об успехе:
  `added` / `skipped` (`reasons`: duplicate, status, missing_fields, amount_unparsed, amount_limit) /
  `suspicious` (`date_unrecognized`); человекочитаемо — `summarize()`; совместимые ключи `dupes`/`invalid`
  сохранены. CLI `spendtrack import … [--json]`.
- **Anonymizer** — `spendtrack anonymize выписка.csv [образец.csv] [--rows N] [--anon-column ФИО]`
  (`spendtrack.anonymize`, dev-обёртка `scripts/anonymize.py`): обезличивает выписку для отправки образца
  (описания/мерчанты → `ОПЕРАЦИЯ_0001`, карты → `КАРТА_0001`, номера документов → порядковый), сохраняя
  формат (шапка/даты/суммы/разделитель/CRLF) — образец остаётся валидной фикстурой. Даты/суммы/категории
  не обезличиваются: предупреждение в stderr, по умолчанию остаются первые 5 строк (`--rows 0` — все).
- **Псевдоним счёта (account_anon)** — `acc_hex8`; сырой номер карты НЕ хранится (`account_pseudonyms`).
- **Примеры (examples)** — few-shot для LLM (правки юзера навсегда).
- **Бюджет** — месячный лимит категории в `budgets(category, amount_kopecks)` (SQLite, не TOML). Одна константа на все месяцы, без rollover. Считаются расходы месяца (знаковая сумма: возвраты уменьшают). Доход/переводы (`BUDGET_EXCLUDED`) не бюджетируются. Пусто/0 = снят. Редактор — `/settings`, прогресс — `/dashboard`, CLI `spendtrack budget`.
- **Демо-режим** — `scripts/demo_data.py seed|status|clean`: детерминированная синтетическая витрина (~5 мес: подписки со скачком цены, крупная сумма и near-дубль, 6 pending, 5 бюджетов, кандидаты suggest-rules). Сеет в `data/demo.db` (реальную БД защищает guard), удаляет строго по манифесту; Codespaces засеивает `seed --if-empty` при первом старте.
- **Установленный режим / user-dir** — запуск без репозитория (`uv tool`/uvx): конфиг и данные в пользовательских
  папках (Windows `%APPDATA%\spendtrack` и `%LOCALAPPDATA%\spendtrack`; Unix `~/.config/spendtrack`,
  `~/.local/share/spendtrack`), дефолты — из пакета (`src/spendtrack/defaults/`, входят в wheel). Repo-режим
  (clone + `uv sync`, прод NSSM) определяется по `config/settings.toml` рядом и сохраняет пути `data/`/`config/`.
  Раскладка — `spendtrack paths [--json]`; запуск — `spendtrack serve [--open]`; переопределение —
  `SPENDTRACK_CONFIG_DIR`/`SPENDTRACK_DATA_DIR`. Bootstrap: `install.ps1`/`install.sh`.
- **Сервис (автозапуск)** — приложение как фоновая служба: шаблоны `deploy/` (systemd --user, launchd) + README
  §«Работа в фоне» (Windows: Планировщик заданий / NSSM). Всегда слушает `127.0.0.1`; конфиг/данные — user-dir
  (`spendtrack paths`), под LocalSystem пути передаются явно через `SPENDTRACK_CONFIG_DIR`/`SPENDTRACK_DATA_DIR`.
- **Doctor** — проверка целостности данных: CLI `spendtrack doctor [--json]`, API `GET /health/data`. Severities: `critical` (битая БД/схема, категории транзакций вне таксономии, последний restore-drill failed), `warn` (данные вне очереди/таксономии, бэкап >48ч, restore-drill >30 дней), `info` (пустые партии, нет папки бэкапов, нет маркера restore-drill), `ok`. Exit 1 — только при critical; API 503 — при critical. Авторемонта нет.
- **Restore-drill** — `scripts/restore_drill.py` (CLI `python -m scripts.restore_drill`): копирует последний `data/backup/spend-*.db` во временную папку, проверяет `PRAGMA integrity_check` + `transactions` + `user_version`, сверяет COUNT/SUM с живой БД информативно, пишет маркер `data/backup/last_restore_drill.json`.
- **Offsite-копия (внешний бэкап)** — копия свежего снимка на другом томе: `scripts/backup.py --copy-to <папка/USB>`
  (guard «тот же диск» через `st_dev`, `--force` — исключение; sha256-проверка; удаление битой копии). Маркер
  `data/backup/last_offsite_copy.json` (`time/source/dest/sha256/size`) читает doctor-чек `offsite_backup`
  (нет маркера → info, файл не найден/старше 7 дней/битый маркер → warn, sha не совпал → critical). Хэш-хелпер — `spendtrack.checksum`.
- **Анонимная сводка (share)** — `spendtrack doctor --share`: метрики-прокси без телеметрии — локально печатает
  счётчики (версии, ОС, режим repo/installed, режим LLM, tx/imported/партии/категории/правила/бюджеты/pending,
  бакет истории, наличие бэкапов) и prefilled-ссылку на issue; ничего не отправляется, пока пользователь сам не
  поделится. Суммы/описания/мерчанты/счета/точные даты/пути/секреты исключены (канон — `PRIVACY.md`).
- **Рекурринг/подписка** — повторяющееся списание: ≥3 расхода мерчанта с суммами в ±5% медианы кластера и интервалами 27–34 дн (медиана 28–31; допускается 1 пропуск месяца: разрыв 56–62 дн). «Цена» = медиана кластера, `active` = последнее списание ≤40 дн назад. Считается на лету, не хранится: CLI `spendtrack recurring [--json]`, карточка на `/dashboard` (`recurring_summary`, JSON-ключ `subscriptions` — не `items`, т.к. в Jinja `dict.items` — метод).
- **Suggest-rules (подсказки правил)** — read-only кандидаты keyword-паттернов из решений человека: явные правки (`category_source='correction'`), переопределения LLM в решённых строках (`review_status='approved'` и `category != category_llm`; pending/skipped игнорируются), `examples`, плюс тип «merchant». Пороги n≥3 / чистота ≥80%, конфликты показываются; статус сверяется с taxonomy.toml (`analyze_rules`): новое/дубль/будет мёртвым/пересечение. CLI `spendtrack suggest-rules [--json]`; записи нет.
- **Экспорт** — выгрузка транзакций без потерь: CLI `spendtrack export [--format csv|xlsx]` (по умолчанию все),
  веб `GET /export.csv|/export.xlsx?month=&category=&q=` (кнопка на главной). CSV — utf-8-sig/«;»/ASCII-минус
  (открывается в Excel), XLSX — openpyxl (нативные типы). `Store.export_transactions()` — `tuple`, без лимита
  страницы; внутренние поля (fingerprint/import_batch) не выгружаются.
- **BYO-LLM/Ollama** — режим «свой LLM»: любой OpenAI-совместимый сервер через `SPENDTRACK_LLM_BASE_URL/MODEL/API_KEY`
  или локальный пресет `SPENDTRACK_LLM_PROVIDER=ollama` (air-gap). При заданном BYO free-цепочка не используется
  вообще (без тихих фолбэков). Статус: `spendtrack llm-status [--json]`; резолв — `resolve_providers()` в `llm.py`.
  Локальные шимы free-цепочки (`localhost:3001/3201`) — только с `SPENDTRACK_ALLOW_LOCAL_LLM=1`.
- **Калибровка порога** — `spendtrack confidence` (`reports.confidence_calibration`): бакеты conf решённых
  LLM-предложений + кандидатные пороги с покрытием/долей ошибок; `wilson_interval()` даёт верхнюю границу
  ошибок (95%), рекомендация — минимальный порог с ошибками ≤10% при ≥20 принятых (data-gated).
- **Помощь (/help)** — страница справки в приложении: быстрый старт, how-to, глоссарий, легенда источников
  категории/статусов/цветов, FAQ (нативные `<details>`), приватность, «Почему так?». Ссылка — в nav на всех
  страницах; структура — по `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` (Diátaxis + WCAG 2.2).
- **Лендинг** — статическая страница `landing/` (GitHub Pages, workflow `pages.yml`; URL `exnihil14.github.io/spend-tracker`):
  оффер, скриншоты витрины, демо-кнопка Codespaces, Supporter ($25/1900₽, mailto + issue) и донат Boosty
  (кнопка выключена до запуска — живой заглушки нет), опрос Telegram-vs-PWA через issue-формы; внешних
  ресурсов и аналитики нет.
- **Prebuilt CSS** — стили собираются заранее (Tailwind standalone CLI, `scripts/build_css.py`) в
  `static/app.css`; browser build (Play CDN) в проде не используется. После правок классов в шаблонах —
  пересобрать (`uv run python scripts/build_css.py`), в CI — `--check`.
- **Периметр** — гейт Origin/Sec-Fetch-Site для state-changing запросов + `TrustedHostMiddleware`
  (`spendtrack/security.py`): чужие Origin/Host → 403/400; CLI/тесты без заголовков пропускаются.
  В Codespaces (`CODESPACES=true`) trusted hosts/Origin/frame-ancestors расширяются доменом форвардинга
  портов (прокси сохраняет публичный Host) — домен GitHub-контролируемый.
- **Соединение на запрос** — SQLite-соединение на HTTP-запрос через `deps.get_store()` (dependency с `yield`):
  закрытие гарантировано, `PRAGMA optimize` перед закрытием.
- **Токены** — `src/spendtrack/tokens.css` (2 слоя: primitives → semantic) — единый источник цветов/радиусов
  для приложения (Tailwind v4 `@theme inline`) и лендинга (копия `landing/tokens.css`); в разметке — только
  semantic-классы (`bg-surface`, `text-fg-muted`, `bg-accent-bg`). Семантика: расходы — нейтральный `text-fg`
  со знаком «−», красный — только перерасход/аномалии/деструктив; один primary-акцент на экран (M-1/M-3).
- **Версия статики** — `/static/<файл>?v=<sha8>` (`assets.static_url()`, Jinja-хелпер `static`): версионированные
  URL кэшируются `immutable`, HTML — `no-store`; Chart.js грузится только на дашборде (`dashboard.js`).
- **Дайджест недели** — read-only сводка за скользящее окно (дефолт 7 дней): расход/доход/баланс и дельты к прошлому окну, топ-5 категорий расхода, самый дорогой день, средний расход/день, очередь pending, ближайшие ожидаемые списания рекуррингов и аномалии. CLI `spendtrack digest [--days N] [--json]`, карточка на `/dashboard`; состояние не хранится.
- **Аномалия** — пометка в дайджесте (только вывод, без алертов и авто-действий): крупная сумма (≥3× медианы |расходов| категории за 90 дней, в категории ≥10 наблюдений, пол 1000 ₽), скачок цены активного рекурринга (≥10% к медиане кластера), near-дубль (один день + мерчант + |сумма|, ≥2 строк — fingerprint не склеил). Переводы не участвуют.

## Правила
- Ядро детерминированное и оффлайн; LLM — единственный шов, всегда инжектируемый в тестах.
- Правило «Суммы = копейки» и «не менять fingerprint-контракт без тестов» — не нарушать.
- Тесты: только швы `classify_with_injectable`, `import_csv(classify=)`, `parse_amount`, `fingerprint`; оффлайн через стаб.