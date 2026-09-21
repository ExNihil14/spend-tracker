# SPEC: PIPELINE Spendtrack — команды и контур верификации

Источник по запуску, тестам, миграциям и правилам проверки (Фаза 1 MASTER_PLAN.md).

## Запуск
```bash
uv run uvicorn spendtrack.main:app --port 8766   # dev-сервер (FastAPI)
uv run spendtrack add -23.45 "MILK"              # CLI: добавить трату с категоризацией
uv run spendtrack import file.csv --bank sber [--json]  # импорт CSV (BANKS-адаптер; отчёт-строка или JSON)
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
uv run python -m scripts.backup [--keep 14] [--copy-to ПАПКА] [--force]  # бэкап + внешняя копия (offsite)
uv run python -m scripts.restore_drill           # restore-drill последнего бэкапа → маркер для doctor
uv run python scripts/contract_delta.py check    # контракт-дельта: API+схема+роуты vs baseline (exit 1 при дрейфе)
uv run python scripts/contract_delta.py snapshot # обновить baseline после осознанного изменения контракта
uv run python scripts/demo_data.py seed          # демо-витрина в data/demo.db (реальная БД не трогается)
uv run python scripts/anonymize.py file.csv [-o out.csv] [--anon-column "ФИО"]  # обезличить образец выписки
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
- Проверки (13): quick_check (critical) · дубли fingerprint (critical) · `user_version==SCHEMA_VERSION` (critical) ·
  категории вне таксономии (`transactions.category` critical; `category_llm` warn только при
  `source != 'llm_pending_review'`; rules/budgets/merchant_cache/examples warn) · дубли `examples`
  (info; P1 #6) · мёртвый `merchant_cache` — мерчант без операций, сверка Python `.upper()`,
  кириллица не в SQLite-UPPER (info; P1 #6) · pending с чужим source (warn) ·
  пустые import_batches (info) · бэкап `data/backup/spend-*.db` (папки нет → info, >48ч → warn, quick_check → critical) ·
  restore-drill `data/backup/last_restore_drill.json` (маркера нет → info, >30 дней → warn, последний прогон failed → critical) ·
  offsite-копия `data/backup/last_offsite_copy.json` (маркера нет → info; файл не найден/старше 7 дней/битый маркер →
  warn; sha256 не совпал → critical).
  Битая БД не роняет прогон: упавший чек становится critical (`db_open`/`не удалось выполнить проверку`).
- Авторемонта нет (read-only; Store на входе до-мигрирует старую схему — это норма).
- История (16.09): doctor нашёл, что задача `spendtrack-backup` не срабатывает (0x800710E0: Principal Interactive +
  `DisallowStartIfOnBatteries=True` + `StartWhenAvailable=False`). Починено: догон пропусков включён, запуск на батарее
  разрешён, `ExecutionTimeLimit=PT1H`; прогон задачи → `LastTaskResult=0`, свежий бэкап, doctor = ok.
  Остаётся осознанно: `LogonType=Interactive` (при пропуске 03:00 задача догоняется при следующем входе в систему).

## Бэкапы: локальный + offsite (#12)
- `python -m scripts.backup [--keep N] [--copy-to ПАПКА] [--force]`: локальный снимок `VACUUM INTO`
  (`data/backup/spend-<UTC>.db`, ротация `--keep`, дефолт 14) + опциональная внешняя копия.
- Offsite-политика: копия обязана быть на **другом томе** (`same_device` через `st_dev`; Windows — серийный
  номер тома) — иначе отказ, кроме явного `--force` (тесты/осознанное исключение). После копирования
  сверяется sha256 (`spendtrack.checksum.sha256_file`); битая копия удаляется, маркер не пишется.
- Маркер `data/backup/last_offsite_copy.json` (`time/source/dest/sha256/size`) читает doctor-чек
  `offsite_backup`; его семантика — в разделе Doctor. Ротация `--keep` внешнюю папку не трогает.
- Инструкция — README/FAQ + /help; `doctor` вызванный без настройки offsite даёт info, не ошибку.
- Тесты: `tests/test_backup_offsite.py` (10, оффлайн; guard/force/sha-мисматч/недоступная папка/
  путь-файл/ротация не трогает внешнюю папку) + offsite-тесты `tests/test_doctor.py` (6).

## Метрики-прокси без телеметрии (#13)
- Решение по приватности: автоматического ping/телеметрии **нет и не будет**; счётчиков установок через
  внешний сервис тоже нет. Метрики-прокси = ① GitHub (звёзды/клоны/скачивания установщика/Codespaces) и
  ② добровольная анонимная сводка: `spendtrack doctor --share` печатает **локально** блок со счётчиками
  и prefilled-ссылку на issue (`usage_issue_url`) — открывает/отправляет сам пользователь (ручной opt-in ping).
- Состав сводки (`doctor.build_usage_summary`): версии (spendtrack/схема/Python), ОС, режим repo/installed,
  режим LLM (off/byo/ollama/free, без ключей и адресов), счётчики (tx/imported/batches/categories_used/
  categories_total/rules/budgets/pending), бакет истории (≤30/31–90/91–365/>365), наличие локального и
  внешнего бэкапа. **Никогда**: суммы, описания, мерчанты, счета, имена категорий, точные даты, пути, секреты.
- `--share` не меняет поведение без флага; сеть не трогается вообще (проверено
  `tests/test_offline.py::test_doctor_share_offline` — под заблокированными сокетами). Тесты:
  `tests/test_share_stats.py` (8, оффлайн, включая «в сводке нет чувствительных значений»).
- Канон приватности — `PRIVACY.md` (§Метрики без телеметрии).

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

## Импорт: дрейф формата и отчёт «добавлено / пропущено / подозрительно» (P1 #1–#2)
- **Дрейф формата.** Перед разбором проверяются обязательные колонки банка (`REQUIRED_COLUMNS`, синонимы;
  пробелы/регистр в заголовках терпимы). Неопознанный банк в `auto` или пропавшие/переименованные колонки →
  `status="format_error"` с `missing_columns`/`found_columns` и просьбой прислать обезличенный образец
  (ссылка на issue; `FORMAT_HINT`). БД и партия импорта не трогаются; CLI — exit 1, UI — красное сообщение.
  Тихий мисс-парсинг («0 добавлено, status ok») исключён. `sniff_bank` узнаёт Сбера и по «Дата платежа»
  (устойчиво при переименовании «Дата операции»).
- **Отчёт** (`csv_import.summarize` — единый текст для CLI и UI): `+N добавлено · S пропущено (причины) ·
  K подозрительно (причины) · банк=…`. Пропущено: `duplicate`, `status` (не проведены банком),
  `missing_fields`, `amount_unparsed`, `amount_limit`; подозрительно: `date_unrecognized` (дата не
  распознана — строка импортируется с пометкой, а не молча). Совместимые ключи `dupes`/`invalid` сохранены,
  добавлены `skipped`/`suspicious`/`reasons`/`suspicious_reasons`.
- CLI: `spendtrack import file.csv [--bank …] [--json]` (по умолчанию человекочитаемая строка).
  Тесты: `tests/test_csv_import.py`, `tests/test_synth_import.py` (переименование и удаление колонки на синтетике).
- Битый JSON-конверт: не-JSON/не-UTF-8 тело → 400, неполные поля → 422 (`_json_payload` в `api.py`;
  live-смоук 21.09 вскрыл 500 на кривой кодировке) — и `/api/import`, и `/api/transactions`.

## Anonymizer выписок (P1 #3)
- `python scripts/anonymize.py выписка.csv [-o out.csv] [--anon-column "ФИО"]`: описания/мерчанты →
  `ОПЕРАЦИЯ_0001`, карты/счета → `КАРТА_0001`, номера документов → порядковый номер; шапка, порядок строк,
  даты, суммы, статусы и разделитель сохраняются — образец остаётся валидной фикстурой для адаптеров.
  Колонки определяются по синонимам (`DESC_ALIASES`/`ACCOUNT_ALIASES`/`DOC_ALIASES`); нераспознанные
  не трогаются и перечисляются в отчёте («проверьте, нет ли личных данных»). Вход utf-8/cp1251, выход utf-8.
  Тесты: `tests/test_anonymize.py` (в т.ч. «обезличенный образец импортируется с теми же датами/суммами»).

## Мультивалютность (#5)
- `transactions.currency` — ISO 4217, миграция v5 (`ALTER … ADD COLUMN … DEFAULT 'RUB'`; старые строки = RUB,
  схема fresh-DB тоже содержит колонку). `normalize_currency()` понимает «₽/руб./rub/$/€/доллар»; незнакомое
  значение в импорте → RUB (не роняем импорт), в API → 422, в CLI (`add --currency`) → argparse-ошибка.
- Дедуп: `fingerprint(..., currency='RUB')` — код добавляется к отпечатку **только для не-RUB**: рублёвые
  отпечатки не изменились (реэкспорт старой выписки = no-op), а равные суммы в разных валютах не склеиваются.
- «Не ломаться»: не-RUB не участвует в ₽-агрегациях — `report_month`/`categories_with_totals`/`report_daily`,
  `budgets_progress`, digest (все окна и аномалии), `detect_recurring`, дневные итоги списка. Курсы не смешиваются.
- UI: код валюты рядом с суммой в списке и очереди (для RUB — как раньше, без кода); экспорт CSV/XLSX —
  колонка «Валюта» после «Суммы» (аддитивно); FAQ `/help` обновлён (основная валюта — ₽, не-RUB не в бюджетах).
- Импорт: адаптеры читают колонку валюты (Sber «Валюта операции», Tinkoff «Валюта», Yandex «currency»);
  колонки нет → RUB.
- Тесты: `tests/test_currency.py` (15, оффлайн: алиасы, миграция v4→v5, fingerprint/дедуп, бюджеты/отчёт/
  дайджест/рекурринги, импорт с колонкой и без, экспорт, API 422, UI, CLI); `test_export.py` — новые индексы.
- Попутный фикс: кастомный pydantic-валидатор (`TxIn.currency`) при 422 падал 500 — `ctx` с объектом ValueError
  не сериализовался; `_json_payload` приводит `ctx` к строкам.

## Калибровка порога авто-приёма (#11, Wilson-CI)
- `reports.wilson_interval(successes, n, z=1.96)` — 95% интервал Wilson (устойчив к 0/n и n/n; n=0 → (0,1)).
  В `confidence_calibration` у каждого кандидата t добавлен `wrong_high` — верхняя граница доли ошибок.
- Рекомендация (`recommendation`): ошибок ≤ `CALIBRATION_TARGET_ERROR` (10%) с 95% уверенностью при
  ≥ `CALIBRATION_MIN_SAMPLE` (20) принятых; выбирается минимальный t (максимальное покрытие). Статусы:
  `ok` (порог), `low_data` (мало принятых), `no_candidate` (безопасных порогов нет). При нуле ошибок граница
  10% достигается на ~35 принятых (Wilson) — поэтому решение по порогу остаётся data-gated.
- CLI `spendtrack confidence`: к каждому t печатает верхнюю границу + «рекомендация: …». Live на проде:
  решённых 2/20 → «набрано меньше 20 принятых решений» (data-gated норма). Тесты: `tests/test_reports.py`
  (+5: табличные значения Wilson + guard-и, параметры рекомендации, рекомендации ok/no_candidate, low_data).

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

## Запуск как сервис (P3 #14)
- Шаблоны: `deploy/spendtrack.service` (systemd --user; `ExecStart=%h/.local/bin/spendtrack serve`,
  `Restart=on-failure`, `WantedBy=default.target`) и `deploy/com.spendtrack.serve.plist` (launchd LaunchAgent;
  `/bin/sh -c 'exec "$HOME/.local/bin/spendtrack" serve'`, `RunAtLoad`+`KeepAlive`, логи `/tmp/spendtrack.{out,err}.log`).
- README §«Работа в фоне (автозапуск)»: Windows — Планировщик заданий (AtLogOn, без администратора) и NSSM
  (служба до входа в систему; под LocalSystem данные/конфиг задаются явно `SPENDTRACK_CONFIG_DIR`/
  `SPENDTRACK_DATA_DIR`); macOS — `launchctl bootstrap gui/$(id -u)`; Linux — `systemctl --user enable --now`
  (+ `loginctl enable-linger` — запуск без входа). Ключи LLM — в окружении сервиса (юнит/`EnvironmentVariables`/
  `AppEnvironmentExtra`); шаблоны секретов не содержат.
- Установленный режим (`uv tool`): шим `~/.local/bin/spendtrack` (Windows `%USERPROFILE%\.local\bin\spendtrack.exe`),
  конфиг/данные — user-dir из `spendtrack paths`, поэтому юниты не задают WorkingDirectory.
- Windows-проверка (live 21.09; прод `spendtrack` не трогали): ① NSSM-служба `spendtrack-svc-check` (шим под
  LocalSystem, порт 8799, temp-данные через env) — `start` → `/health` 200 (0 tx) → `restart` → 200 →
  `stop` (порт свободен) → `remove` (служба исчезла; в temp-данных `spend.db`/`logs` — user-dir сработал).
  ② Планировщик: задача AtLogOn `spendtrack-svc-check` — `Start` → `/health` 200 → `Stop`/`Unregister`
  (задача удалена, слушателя не осталось). Прод 8766 — `/health` 200 (8 tx).
- Тесты: `tests/test_deploy_templates.py` (4, оффлайн: структура юнита/plist через `plistlib`, отсутствие
  заглушек/секретов, README ссылается на шаблоны и все три ОС).

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

## Помощь (/help)
- Роут `/help` (`routers/frontend.py`) + шаблон `templates/help.html`: быстрый старт (4 шага), «Как сделать…»,
  глоссарий (15 терминов), легенда источников категории/статусов/цветов, 22 FAQ на нативных `<details>` (без JS),
  «Данные и приватность», «Почему так?», ссылки. Порог авто-приёма и число категорий берутся из конфига
  (справка не расходится с поведением).
- Структура и правила — по ресёрчу `D:\dev\docs\machine\RESEARCH_HELP_FAQ_BEST_PRACTICES.md` (Diátaxis-квадранты,
  2 уровня progressive disclosure, WCAG 2.2: Consistent Help 3.2.6, Use of Color 1.4.1, нативные details/summary).
- Ссылка «Помощь» в nav (`base.html`) — на всех страницах в фиксированной позиции (после «Подтвердить»).
- Тесты: `tests/test_help.py` (3, оффлайн) + e2e `test_help_page_nav_and_faq`; FAQPage JSON-LD не внедряем
  (Google снял rich results 07.05.2026).

## UX-полировка: пустые состояния, подсказки, знаки сумм (P2 #7–#9)
- **Суммы в UI** — `fmt_amount_signed` (`store.py`): явный `+`/`−` (типографский U+2212), ноль «0.00» —
  знак, а не только цвет (WCAG 1.4.1). **Машинная** форма `fmt_amount` (ASCII-минус, без плюса) остаётся
  для CSV-экспорта/промптов/CLI; `parse_amount` понимает обе. В шаблонах — только через эти хелперы.
  Бюджеты (лимит/инпут) намеренно в plain-форме: лимит — не доход, в `input value` знак не нужен.
- **Контраст бейджей** — `colors.py`: `badge_text_color(bg)` выбирает `#020617`/`#ffffff` по контрасту;
  применён в `tx_rows`, `review_rows`, `dashboard` (бюджеты), `/settings` (категории, бюджеты).
  Тесты `tests/test_colors.py`: все 18 дефолтных цветов taxonomy ≥4.5:1; счётчик очереди
  (amber-300 на `amber-500/20` поверх slate-950) ≈10.4:1. Для пользовательских цветов выбирается лучший
  из двух вариантов (гарантии ≥4.5:1 для произвольного цвета нет — это осознанно).
- **Пустые состояния обучающие**: список различает «нет данных вообще» (`has_any=false` → как импортировать),
  «нет по фильтру» (сброс) и «пустой месяц»; очередь — «Все подтверждены» + `/help#faq-queue-why`;
  дашборд при 0 транзакций — онбординг-карточка `#onboarding` (флаг `has_data`), пустой месяц — заметка.
  Флаги — `sum(store.counts().values()) > 0` (`category_source` NOT NULL ⇒ сумма = все строки).
- **Микро-подсказки** (≤1 строка + якорь): импорт → `/help#faq-import-sber`; очередь → `/help#faq-queue-why`
  (порог авто-приёма берётся из конфига).
- Пустое состояние очереди — общий partial `partials/review_empty.html` (используется и шаблоном,
  и OOB-ответом `api._oob_empty_state`, чтобы разметка не расходилась).
- Тесты: `tests/test_ui_polish.py` + `test_colors.py` + дополнения `test_amounts.py`/`test_digest.py`
  (знаки аномалий: медианы хранятся магнитудами — знак расхода ставится явно); e2e
  `tests/e2e/test_ui_polish_e2e.py`. Источник формулировок — `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` §4/§6.

## Первый запуск: чек-лист 4 шага (P2 #10)
- Главная при `first_run` (нет транзакций И нет партий импорта) показывает `#start-checklist`
  (`partials/start_checklist.html`): 4 шага со ссылками (#import/#add, /approve, /settings, /dashboard) +
  `/help#quick-start`. Состояние серверное (`Store.counts()` + `Store.batch_count()`), localStorage не нужен;
  после первых данных (импорт или ручное добавление) чек-лист исчезает — не навязывается активному пользователю.
- Тесты: `tests/test_ui_polish.py` (3: показ 4 шагов со ссылками; скрытие после партии импорта; после ручного add)
  + e2e `test_first_run_checklist_visible_then_hidden` (виден на пустой БД, скрыт после данных).
  Попутно e2e-`clean_db` чистит `import_batches` — состояние партий не течёт между session-scoped тестами.

## Бенчмарк производительности (perf-pass, 21.09)
- Инструмент: `uv run python scripts/bench.py run [--sizes 5000,20000,50000] [--repeats 3] [--import-rows 5000]`
  — детерминированная синтетика (36 мес, подписки/очередь/бюджеты) в temp-БД, median-замеры ключевых путей,
  HTTP через TestClient; JSON — `reports/bench.json`. Прод не трогает.
- Оптимизации по замерам: `month_bounds()` — диапазон `date >= / <` вместо `substr(date,1,7)=?` (использует
  индекс); partial-индекс `idx_tx_pending` (создаётся после миграций — колонка `review_status` из v2; в SCHEMA
  индекс ронял апгрейд легаси-БД); O(1)-медиана кластеров в `detect_recurring`; `detect_recurring` один раз
  на `/dashboard` (параметр `subscriptions=` у `recurring_summary`/`build_digest`); `Store.has_transactions()`
  (EXISTS) вместо `counts()` для флагов страниц; `add_transaction(commit=False)` в `import_csv` — одна
  транзакция на партию; при сбое в середине — `rollback` (партия атомарна, открытой транзакции не остаётся).
- Факты 50K строк (до → после): `/dashboard` 2.75 с → 388 мс, `/` 521 → 73 мс, очередь 245 → 2 мс, месячные
  агрегаты ≈93 → 5 мс, `build_digest` 1.17 с → 365 мс, импорт 5K строк 1.67 с → 0.40 с. Отчёт с таблицей —
  `D:\dev\docs\machine\PERF_BENCH_SPENDTRACKER.md`.
- Перф-смок в наборе: `tests/test_perf.py::test_digest_20k_synthetic` (маркер perf, порог 2 с; длительности —
  `reports/perf.json`).

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
- e2e + htmx: после AJAX-swap НЕЛЬЗЯ ждать `.htmx-request` как признак готовности — он снимается до settle,
  а новый контент получает обработчики htmx только через `defaultSettleDelay=20ms` (`makeAjaxLoadTask` → `processNode`).
  Маркер незрелого контента — `.htmx-added` (снимается в том же settle). Без этого `fill` попадает в инпут без
  слушателей и baseline `changed` фиксируется на введённом значении: превью-запрос не уходит вовсе
  (флейк CI 20.09, 4 пуша подряд; хелпер `_wait_single` в `tests/e2e/test_settings_e2e.py`,
  регресс-тест `tests/e2e/test_htmx_settle.py`).

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