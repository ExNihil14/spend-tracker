# SPEC: Тестирование Spendtrack — стратегия и организация

Источник для агентов: что и как тестируется, как запускать, где пробелы. Основан на аудите
тестирования (23.09.2026, роль QA-лида): `D:\dev\docs\machine\AUDIT_TESTING_SPENDTRACKER.md`.

## Принципы
1. **Тесты — на публичный интерфейс** (CLI `cli.main([...])`, HTTP-роуты, публичные методы `Store`),
   не на внутренности: рефакторинг реализации не красит тесты, AI-правки безопаснее.
2. **Оффлайн-контур**: сеть запрещена — LLM всегда стаб/инжект (`classify=`, `llm_getter`),
   доказательство — `tests/test_offline.py` (блокировка сокетов/DNS).
3. **Пирамида**: unit — основной слой (быстро, изолированно, `tmp_path` + env);
   e2e — только пользовательские флоу в браузере; JS-юнитов нет (app.js/dashboard.js малы, покрыты смоуком).
4. **Рельсы против дрейфа AI-правок**: контракт-гейт `scripts/contract_delta.py` (схема БД + AST-сигнатуры
   ядра + OpenAPI-роуты vs `spec/contract_baseline.json`) — блокер при расхождении; при осознанном
   изменении контракта `snapshot` в том же коммите.
5. **Детерминированность**: e2e ждёт события htmx (`_wait_single` c `.htmx-added`), а не фиксированные
   паузы; тесты не зависят от порядка запуска (autouse `clean_db`, `tmp_path`).

## Уровни и маркеры
| Уровень | Запуск | Что покрывает |
|---|---|---|
| Unit (по умолчанию) | `uv run pytest` | Store/категоризация/импорт/отчёты/CLI/роуты (TestClient), ~30 с |
| E2E (chromium) | `uv run pytest tests/e2e -m e2e` | UI-флоу: импорт, очередь, настройки, дашборд, фильтры, экспорт (~30 с) |
| Кросс-браузерный смоук | `uv run pytest tests/e2e/test_crossbrowser_smoke.py -m e2e --browser firefox --browser webkit` | рендер/консоль 5 страниц, 320px reflow, axe critical+serious=0 |
| Perf | `uv run pytest -m perf` | `test_digest_20k_synthetic` (порог 2 с) → `reports/perf.json` |
| Контракт | `uv run python scripts/contract_delta.py check` | дрейф схемы/сигнатур/роутов |
| Статика | `uv run ruff check src tests scripts`, `uv run python scripts/build_css.py --check` | lint, CSS-артефакт |
| Покрытие (по запросу) | `uv run --with coverage coverage run -m pytest -q` + `coverage report --include="src/spendtrack/*"` | замер, без постоянной зависимости |

CI (`.github/workflows/ci.yml`): lint+unit, e2e (chromium), cross-browser smoke (firefox+webkit),
contract, pip-audit, secret-scan. Перед коммитом — unit + ruff; перед отчётом о готовности — живой прогон.

## Текущее состояние (25.09.2026)
- **581 unit + 52 e2e** (+ cross-engine прогоны), все оффлайн; покрытие `src/spendtrack` — **96%**.
- **§G-4/5 (25.09):** golden-набор `tests/golden/merchants.csv` + `scripts/golden_report.py` (read-only,
  `reports/golden.json`; база: 34/34 rule-хитов, 6 нерешённых, 0 ошибок) — `tests/test_golden_report.py`;
  конкурентный HTTP-смоук (`tests/test_concurrent_http.py`); e2e жизненного цикла категории
  (`test_settings_e2e.py`).
- **Property-based и chaos (§G, 25.09):** `tests/test_property_parsers.py` (hypothesis: `parse_amount`,
  `sniff_bank`, `import_csv` — инвариант «любой ввод → валидная запись или `_skip` с известной причиной,
  никогда исключение; даты в БД только ISO») и `tests/test_import_chaos.py` (CR в поле, CRLF/cp1251/битые
  байты, 20K-описание, лимит 10 МБ, пустышки, случайные байты, параллельная UI-запись во время импорта).
  Фикстуры миграций v3/v4 (`test_migrations.py`): данные/бюджеты сохраняются, валюта бэкфиллится,
  повторное открытие идемпотентно. Найдены и закрыты реальные дефекты: падение csv-парсера на одиночном
  `\r`; `parse_amount("nan"/"inf")` → контролируемая `InvalidOperation` (CLI exit 1).
- Ядро (store/categorize/csv_import/reports/digest/recurring/export/security), очереди, бюджеты, калибровка,
  doctor, бэкапы/restore-drill/offsite, периметр, offline/BYO-LLM, лендинг, деплой-шаблоны, контракт — покрыто.
- **P0 аудита закрыт** (`tests/test_cli_commands.py`, ветки 4xx в `test_api.py`, роуты категорий в
  `test_settings.py`, `/health` 503, `update_merchant`/`needs_review`): cli.py 85→90%, api.py 92→97%,
  settings.py 89→95%, main.py 91→94%.
- **P1/P2-малые закрыты:** HX-ветки импорта (empty/generic/лимит, `test_api.py`); e2e XLSX-скачивания
  и мультивалютности (`test_smoke.py`); фиксированные паузы заменены детерминированными ожиданиями
  (`wait_for_load_state("networkidle")`, `expect_response` в `test_htmx_settle.py`); seed-хелперы e2e
  дедуплицированы в `tests/e2e/helpers.py` (через публичный `Store`, не raw SQL); `anonymize.py` 80→99%
  (CLI + пустой ввод). `backup.py` 97% — остаток (80, 131) это `__main__`-гард и reconfigure-ветка, не тестируются.
- **Бэклог (остаток P1/P2):** property-based `fingerprint`/`month_bounds`; параметризация матриц
  (валюты/банки); e2e «Показать ещё» (keyset, активируется в многомесячном режиме); inline raw-SQL блоки
  в отдельных e2e (можно перевести на helpers).

## Property-based (hypothesis)
- `hypothesis` — dev-зависимость; файлы: `tests/test_property_parsers.py`, `tests/test_import_chaos.py`.
- Пишем **инварианты, не примеры**: «любой ввод → валидная запись или `_skip` с известной причиной, никогда
  исключение»; «даты в БД только ISO (`GLOB '____-__-__'`)»; roundtrip `parse_amount(fmt_amount(k)) == k`.
- Настройки: `max_examples=60–80`, `deadline=None`; для функциональных фикстур — suppress
  `function_scoped_fixture`; лимиты входа защищать `assume(len(blob) < MAX_CSV_BYTES)`.
- Свойство, найденное багом, сначала закрепляем обычным регресс-тестом, затем фикс (пример: CR в поле,
  «nan» в сумме).

## Как добавить тест
1. Выбери **публичный интерфейс**: CLI-команда → `cli.main([...])` + `capsys`; роут → `TestClient(app)`
   с env-БД (`SPENDTRACK_DB_PATH` в `tmp_path`); логика → метод `Store`.
2. Данные — через `Store.add_transaction(...)`/фикстуры, не raw SQL (raw SQL только для проверки миграций).
3. AAA + один смысловой ассерт на тест; для e2e — `expect` (web-first) и ожидание htmx-событий.
4. Новый тест на регресс — обязательно с комментарием, **что именно ломалось** (пример: фильтр категории
   протекал в `list_transactions_days`).

## Чего НЕ тестировать (анти-овер-инжиниринг)
- UI для бэкапов/doctor (это CLI/API), реальный Safari/iOS/Yandex, нагрузка/APM, сетевой e2e с LLM,
  CSRF-токены (нет сессий; периметр Origin/Host закрыт), тесты на SQL-тексты/приватные хелперы,
  мутационное тестирование, отдельный JS-юнит-слой.
