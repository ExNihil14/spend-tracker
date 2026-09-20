# SPEC: PIPELINE Spendtrack — команды и контур верификации

Источник по запуску, тестам, миграциям и правилам проверки (Фаза 1 MASTER_PLAN.md).

## Запуск
```bash
uv run uvicorn spendtrack.main:app --port 8766   # dev-сервер (FastAPI)
uv run spendtrack add -23.45 "MILK"              # CLI: добавить трату с категоризацией
uv run spendtrack import file.csv --bank sber    # импорт CSV (BANKS-адаптер)
uv run spendtrack report --month 2026-09         # отчёт за месяц
uv run spendtrack count                          # счётчики
uv run spendtrack budget --month 2026-09         # прогресс по бюджетам категорий
uv run spendtrack confidence                     # калибровка порога авто-приёма LLM
uv run spendtrack llm-status [--json]            # режим LLM: off/byo/ollama/free (без сети и ключей)
uv run spendtrack serve [--host 127.0.0.1] [--port 8766] [--open]  # веб-интерфейс (uvicorn)
uv run spendtrack paths [--json]                 # раскладка конфиг/данные/БД + режим (repo/installed)
uv run spendtrack export [--format csv|xlsx] [--month YYYY-MM] [--out FILE]  # выгрузка транзакций
uv run spendtrack doctor [--json]                # целостность данных (exit 1 только на critical)
uv run spendtrack recurring [--json]             # детекция рекуррингов/подписок
uv run spendtrack suggest-rules [--json]         # подсказки keyword-правил из правок (read-only)
uv run spendtrack digest [--days N] [--json]     # дайджест недели + флаги аномалий (read-only)
uv run python -m scripts.restore_drill           # restore-drill последнего бэкапа → маркер для doctor
uv run python scripts/contract_delta.py check    # контракт-дельта: API+схема+роуты vs baseline (exit 1 при дрейфе)
uv run python scripts/contract_delta.py snapshot # обновить baseline после осознанного изменения контракта
uv run python scripts/demo_data.py seed          # демо-витрина в data/demo.db (реальная БД не трогается)
```

## Экспорт CSV/XLSX (read-only, «выход без потерь»)
- CLI `spendtrack export [--format csv|xlsx] [--month YYYY-MM] [--category] [--search] [--from/--to] [--out FILE]`
  — по умолчанию **все** транзакции; файл `spend-export-<дата>.<ext>`.
- Веб: `GET /export.csv|/export.xlsx?month=&category=&q=` (кнопка «Экспорт CSV» на главной; на ссылке обязателен
  `hx-boost="false"` — иначе `hx-boost` на `<body>` перехватывает клик и скачивание не происходит).
- CSV: utf-8-sig (BOM — Excel видит кириллицу), разделитель «;», CRLF, суммы ASCII-минус/точка (`-123.45`);
  поля: дата, описание, сумма, категория, источник, уверенность, мерчант, счёт, статус, предложение LLM
  (внутренние fingerprint/import_batch не выгружаются).
- Защита от CSV/formula-инъекций: текстовые поля с ведущими `= + - @` (tab/CR) получают префикс `'` —
  Excel/Sheets не исполняют их как формулы; суммы не трогаются (строгий числовой формат).
- XLSX (openpyxl): нативные дата/число (формат `#,##0.00`), жирная шапка, автофильтр, freeze panes.
- Store: `export_transactions()` — `tuple[dict, ...]`, без лимита страницы списка (500). Тесты:
  `tests/test_export.py` (14, оффлайн) + e2e скачивания (`test_export_csv_link_downloads`).

## Демо-данные (витрина)
- `scripts/demo_data.py`: `seed [--if-empty] [--force] [--db PATH]` / `status` / `clean` — детерминированный
  синтетический профиль (~5 месяцев): подписки (включая скачок цены), крупная сумма и near-дубль (аномалии),
  6 pending, 5 бюджетов (перерасход/80%), corrections/examples → кандидаты `suggest-rules`, партия импорта.
- По умолчанию — `data/demo.db`; guard: `spend.db` и непустые БД требуют `--force` (осознанно).
  `seed --date YYYY-MM-DD` — воспроизводимые скриншоты/тесты (фиксированная дата). `clean` удаляет строго по манифесту
  (`data/demo.db.demo_manifest.json`). `seed` заканчивается `verify` — все витринные фичи обязаны быть на месте.
- Codespaces: `start-app.sh` вызывает `seed --if-empty` — свежий стенд сразу показательный.
- Стенд: `SPENDTRACK_DB_PATH=data/demo.db uv run uvicorn spendtrack.main:app --port 8767`.
- Тесты: `tests/test_demo_data.py` (4, оффлайн; фиксированная дата → детерминированные окна дайджеста).

## Doctor (целостность данных)
- CLI `spendtrack doctor` — таблица чеков; `--json` — машинный JSON; exit 0 = ok/warn, 1 = critical.
- API `GET /health/data` → `{status, checks:[{id, severity, count, detail}]}`; 503 при critical.
  `GET /health` (liveness) — отдельный эндпоинт, не трогать.
- Проверки: quick_check (critical) · дубли fingerprint (critical) · `user_version==SCHEMA_VERSION` (critical) ·
  категории вне таксономии (`transactions.category` critical; `category_llm` warn только при
  `source != 'llm_pending_review'`; rules/budgets/merchant_cache/examples warn) · pending с чужим source (warn) ·
  пустые import_batches (info) · бэкап `data/backup/spend-*.db` (папки нет → info, >48ч → warn, quick_check → critical) ·
  restore-drill `data/backup/last_restore_drill.json` (маркера нет → info, >30 дней → warn, последний прогон failed → critical).
  Битая БД не роняет прогон: упавший чек становится critical (`db_open`/`не удалось выполнить проверку`).
- Авторемонта нет (read-only; Store на входе до-мигрирует старую схему — это норма).
- История (16.09): doctor нашёл, что задача `spendtrack-backup` не срабатывает (0x800710E0: Principal Interactive +
  `DisallowStartIfOnBatteries=True` + `StartWhenAvailable=False`). Починено: догон пропусков включён, запуск на батарее
  разрешён, `ExecutionTimeLimit=PT1H`; прогон задачи → `LastTaskResult=0`, свежий бэкап, doctor = ok.
  Остаётся осознанно: `LogonType=Interactive` (при пропуске 03:00 задача догоняется при следующем входе в систему).

## Рекурринги/подписки (read-only)
- CLI `spendtrack recurring [--json]` + карточка «Подписки / рекурринги» на `/dashboard` (вся история).
- Критерий: ≥3 расхода мерчанта, суммы в ±5% медианы кластера (жадная кластеризация; «цена» = медиана),
  интервалы 27–34 дн (медиана 28–31), допускается 1 пропуск месяца (разрыв 56–62 дн); переводы не участвуют.
- `active` — последнее списание ≤40 дн от сегодня; месячный итог считает только активные.
- Ничего не хранится (вычисление на лету), авто-действий нет; JSON-ключ `subscriptions` (не `items` — Jinja).
- Тесты: `tests/test_recurring.py` (17 unit, оффлайн) + e2e карточки `test_dashboard_recurring_card`.

## Suggest-rules (подсказки keyword-правил, read-only)
- CLI `spendtrack suggest-rules [--json]`: кандидаты из решений человека — `category_source='correction'`,
  переопределения LLM в **решённых** строках (`review_status='approved'` и `category != category_llm`; pending/skipped
  не считаются), `examples`; плюс тип «merchant» (полное имя мерчанта). Паттерны — униграммы/биграммы
  нормализованных описаний (UPPER, без цифр и токенов <3 символов).
- Пороги по умолчанию: n≥3 подтверждений, чистота ≥80% (конфликты категорий показываются, не скрываются).
  Статус сверяется с taxonomy.toml через `analyze_rules`: новое / дубль / будет мёртвым / пересечение.
- Ничего не записывается (TOML/БД не трогаются). Тесты: `tests/test_suggestions.py` (9, оффлайн);
  на проде без правок ожидаем «предложений нет» — data-gated норма.
- Doctor-фикс 17.09 (найден стрессом флейка): `_guarded` переводит **любое** упавшее исключение чека в critical,
  `quick_check` отдельно обрабатывает «PRAGMA упал» (malformed) — doctor не роняется на повреждённых данных.

## Контракт-дельта (авто-гейт)
- `scripts/contract_delta.py` — снапшот публичных контрактов: схема БД (user_version + колонки из tmp-БД Store),
  публичные сигнатуры `src/spendtrack` (AST, без импорта), HTTP-роуты (OpenAPI). Baseline: `spec/contract_baseline.json`.
- Команды: `snapshot` (обновить baseline), `check` (exit 1 при дрейфе). CI-шаг «Contract delta» в `lint-and-test`.
- Поток при осознанном изменении контракта: изменить код → `snapshot` → baseline в том же коммите. При AI-рефакторинге
  расхождение check = блокер (LLM молча выкидывают функциональность; happy-path тесты это не ловят).
- Тесты: `tests/test_contract_delta.py` (6, оффлайн, герметичные — tmp-пакеты/файлы baseline).

## Офлайн-first, лимиты импорта, очередь (фаза 0 аудита 19.09)
- LLM по умолчанию **выключен**. Резолв — `resolve_providers()`; режимы: BYO (`SPENDTRACK_LLM_BASE_URL/MODEL/API_KEY`,
  любой OpenAI-совместимый сервер), Ollama (`SPENDTRACK_LLM_PROVIDER=ollama`, air-gap), free-цепочка (ключи;
  локальные шимы 3001/3201 — дополнительно `SPENDTRACK_ALLOW_LOCAL_LLM=1`, строго, даже при ключе). BYO вытесняет
  free-цепочку и в неё не откатывается. Статус: `spendtrack llm-status [--json]`. Доказательство: `tests/test_offline.py`
  (офлайн + BYO при заблокированной сети) и `tests/test_llm_byo.py` в CI.
- Лимиты импорта: CSV ≤ 10 МБ (`MAX_CSV_BYTES`), |сумма| > 1 млрд ₽ → строка в отчёт `invalid` (`MAX_AMOUNT_KOPECKS`);
  API отдаёт 413 c понятным текстом, CLI — код 1.
- Фикс 19.09: `import_csv` переносит `review_status`/`category_llm` из классификатора — низкоуверенные импортные
  строки теперь реально попадают в очередь (раньше были «approved» без предложения LLM).
- Фикс 20.09 (найден live-прогоном BYO на Ollama): CLI `add` сохраняет результат классификатора целиком
  (`category_source`/`confidence`/`category_llm`/`review_status`) — низкоуверенные строки из CLI тоже идут
  в очередь и видны калибровке; тесты `tests/test_cli_add.py` (3).
- Приватность/угрозы: `PRIVACY.md`, `SECURITY.md` в корне.

## Дайджест недели + аномалии (read-only)
- CLI `spendtrack digest [--days N] [--json]` + карточка «Дайджест недели» на `/dashboard`; ничего не хранится,
  вычисление на лету (модуль `src/spendtrack/digest.py`).
- Окно rolling [today-days+1..today] (дефолт 7), сравнение с предыдущим окном той же длины; `transfers` исключены
  везде, доход — только в итогах. Топ-5 категорий расхода с дельтами, самый дорогой день, средний расход/день,
  очередь pending, ближайшие ожидаемые списания рекуррингов (`next_expected` <=14 дн).
- Аномалии (топ-10 по score): `large_expense` (>=3x медианы |расходов| категории за 90 дней, в категории >=10
  наблюдений, пол 1000 ₽), `price_jump` (первое отклоняющееся >=10% списание после активного рекурринг-кластера),
  `near_duplicate` (date+merchant+|amount|, >=2 строк — fingerprint не склеил). Только пометки, без алертов/ML/записей.
- Тесты: `tests/test_digest.py` (27 unit, оффлайн) + e2e карточки `test_dashboard_digest_card`.

## One-command установка (волна 3, шаг 3)
- Bootstrap: `install.ps1` (Windows) / `install.sh` (Unix/WSL) — проверяют uv (при отсутствии ставят
  официальным установщиком astral.sh; uv сам поставит Python 3.13), затем `uv tool install git+https://github.com/ExNihil14/spend-tracker`
  и `spendtrack serve --open`. Флаги: `-NoServe`/`--no-serve`, `-Source`/позиционный аргумент (локальный wheel/путь — для проверок).
- Установленный режим (uv tool/uvx): пакет в venv инструмента, конфиг/данные — в пользовательских папках
  (Windows: `%APPDATA%\spendtrack`, `%LOCALAPPDATA%\spendtrack`; Unix: `~/.config/spendtrack`, `~/.local/share/spendtrack`).
  `SPENDTRACK_CONFIG_DIR`/`SPENDTRACK_DATA_DIR` переопределяют оба корня. При первом `serve`/правке таксономии
  дефолты (`src/spendtrack/defaults/{settings,taxonomy}.toml`, входят в wheel) копируются в config-каталог
  (существующие файлы не перезаписываются).
- Repo-режим (clone + `uv sync`, прод NSSM): определяется по `config/settings.toml` рядом с репозиторием — пути
  остаются прежними (`data/`, `config/`), поведение прода не меняется.
- Проверки/разработка: `uv tool install --force ./dist/spendtrack-<ver>-py3-none-any.whl`,
  `uv tool run --from . spendtrack paths` (сборка из рабочего дерева без публикации).
- Docker (опционально): `Dockerfile` (образ `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`, `uv sync --frozen --no-dev`,
  `SPENDTRACK_DATA_DIR=/data`, `SPENDTRACK_CONFIG_DIR=/data/config`); запуск:
  `docker run --rm -p 127.0.0.1:8766:8766 -v spendtrack-data:/data spendtrack`.
- Исторический фикс 20.09: `httpx` был только в dev-группе, а `llm.py` импортирует его на уровне модуля —
  wheel-установка падала на `ModuleNotFoundError`; теперь `httpx` в runtime-зависимостях.

## Лендинг + демо-кнопка (GitHub Pages)
- `landing/` — статический лендинг (RU + EN-блок): оффер, скриншоты демо-витрины (`assets/shot-*.png`),
  «60 секунд»-путь установки, демо-кнопка Codespaces, Supporter-блок (mailto + issue), Boosty, опрос
  Telegram-vs-PWA (issue-формы), FAQ и приватность. Внешних ресурсов нет (шрифты/CDN/аналитика) — без сети.
- Деплой: `.github/workflows/pages.yml` при push в `main` с изменениями в `landing/**` (source — GitHub Actions;
  Pages включён через `gh api repos/ExNihil14/spend-tracker/pages -X POST -f build_type=workflow`).
  URL — <https://exnihil14.github.io/spend-tracker/>.
- Локальный предпросмотр: `python -m http.server 8788 --directory landing` → <http://127.0.0.1:8788/>.
- Скриншоты для лендинга снимаются со стенда демо-данных (`scripts/demo_data.py seed` + сервер 8767).
- Перед запуском заменить заглушку Boosty в трёх местах: `landing/index.html`, `README.md`, `.github/FUNDING.yml`
  (`https://boosty.to/REPLACE_ME`).
- Механики: `mailto:exnihil88@gmail.com` (контакт автора из pyproject); опрос/Supporter/баги —
  `.github/ISSUE_TEMPLATE/{poll-pwa,poll-telegram,supporter,bug-report}.yml` (лейблы `poll`, `supporter`).
- Тесты: `tests/test_landing.py` (оффлайн: отсутствие внешних ресурсов, существование локальных ссылок/ассетов,
  наличие демо-кнопки/почты/опросов, workflow и FUNDING на месте).

## Тесты / анализ
```bash
uv run pytest -q                # unit-тесты (e2e отдельно: uv run pytest tests/e2e -m e2e), все оффлайн (LLM-стаб)
uv run ruff check               # lint, чистый
```
Правила Фазы 2 (контур верификации):
- Commit ПЕРЕД началом задачи, diff ПОСЛЕ.
- Визуальная проверка в браузере для ЛЮБОГО UI-изменения (не только pytest).
- Smoke-тест полного сценария обязателен: POST /transactions (live LLM) → GET / (htmx-отображение).
- Ревью — по чек-листу дисциплины данных (`D:\dev\docs\machine\REVIEW_CHECKLIST.md`): границы/мутации/контракты/тесты/
  контракт-дельта; включать пункты в header ревью-промпта. Формат вывода — **план пунктами** (P0/P1 с фактами),
  галочки исполнителя проходят независимую верификацию. Скилл агента-исполнителя — `data-discipline` (после рестарта opencode).
- Брифы субагентам — по шаблону `D:\dev\docs\machine\TASK_BRIEF_TEMPLATE.md` (чек-лист задачи внутри:
  контракт-дельта, миграции, usage-first тесты, дисциплина данных, гейт, доки).
- Ревью WIP автоматизировано: `uv run python scripts/review.py --title "..." [--notes facts.md] [--out review.md]`
  — сам собирает чек-лист + план-формат + `git diff` (+untracked) и вызывает OpenRouter :free ($0);
  для длинных прогонов запускать через `start-detached.ps1`. Прогресс/готовность — по файлу `--out`.

## Миграции
- Аддитивные: новый путь рядом со старым, переключение ПОСЛЕ подтверждённой работы,
  удаление старого — последним шагом.
- SQLite WAL: отдельный процесс бэкапа не гонять параллельно с записью (см. README Task Scheduler).

## Применение изменений в проде (NSSM `spendtrack`, 8766)
- Python-код загружается при старте процесса: изменения в `src/` вступают в силу ТОЛЬКО после
  `nssm restart spendtrack` (на этой машине, в PowerShell — я запускал; можно и через services.msc → Restart).
- **Шаблоны Jinja перечитываются на лету** (auto_reload): правка `.html` применяется без рестарта.
  Отсюда ловушка: шаблон может начать ссылаться на новые переменные контекста раньше, чем рестартнётся Python
  (наблюдалось 16.09: стрелки `?month=` вместо `?month=YYYY-MM`). **Правило: после правок, затрагивающих
  и шаблоны, и код, — сразу перезапускать сервис.** Проверка после рестарта: `/health`, затронутая страница
  живым запросом (не только 200), и для миграций — `PRAGMA user_version`.

## LLM-провайдеры (полный маршрут)
Резолв — `resolve_providers()` (`src/spendtrack/llm.py`); канон — `spec/ARCHITECTURE.md` §LLM-маршрут:
1. BYO (`SPENDTRACK_LLM_BASE_URL/MODEL/API_KEY`) — свой OpenAI-совместимый сервер; единственный провайдер, без фолбэков.
2. Ollama (`SPENDTRACK_LLM_PROVIDER=ollama`) — локально (air-gap), модель `llm.offline` (qwen2.5-coder:3b).
3. free-цепочка (ключи; локальные шимы — дополнительно `SPENDTRACK_ALLOW_LOCAL_LLM=1`): OpenRouter :free →
   FreeLLMAPI (localhost:3001) → abacus-web shim (127.0.0.1:3201, deepseek-v4-1-flash, токен TTL 1ч).
4. Офлайн-правила/кэш — без сети.
Ключ подбирается под URL (openrouter → OPENROUTER-ключ, иначе FreeLLM-ключ). Статус: `spendtrack llm-status`.

## Правило
- Отчёт агента не принимается без проверки по логам/живому ответу (не «галлюцинировать готово»).