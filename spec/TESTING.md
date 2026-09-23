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

## Текущее состояние (23.09.2026)
- **499 unit + 46 e2e** (+ 40 cross-engine прогонов), все оффлайн; покрытие `src/spendtrack` — **96%**
  (после P0-тестов аудита; было 95%).
- Полностью/почти покрыто: ядро (store/categorize/csv_import/reports/digest/recurring/export/security),
  очереди, бюджеты, калибровка, doctor, бэкапы/restore-drill/offsite, периметр, offline/BYO-LLM, лендинг,
  деплой-шаблоны, контракт.
- **P0 аудита закрыт** (`tests/test_cli_commands.py`, ветки 4xx в `test_api.py`, роуты категорий в
  `test_settings.py`, `/health` 503, `update_merchant`/`needs_review`): cli.py 85→90%, api.py 92→97%,
  settings.py 89→95%, main.py 91→94%.
- **Бэклог (P1/P2, из аудита):** e2e настроек категорий; e2e «Показать ещё» (keyset); e2e XLSX-скачивания;
  e2e мультивалютности; property-based (`hypothesis` — `parse_amount`, `fingerprint`, `month_bounds`);
  HX-ветки импорта; дедуп seed-хелперов e2e; параметризация матриц (валюты/банки); покрытие скриптов
  (`anonymize.py`, `backup.py`); смоук конкурентных HTTP.

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
