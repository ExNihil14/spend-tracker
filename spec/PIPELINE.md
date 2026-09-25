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
uv run spendtrack backup [--keep 14] [--copy-to ПАПКА] [--force]  # бэкап + внешняя копия (offsite)
uv run python -m scripts.restore_drill           # restore-drill последнего бэкапа → маркер для doctor
uv run python scripts/contract_delta.py check    # контракт-дельта: API+схема+роуты vs baseline (exit 1 при дрейфе)
uv run python scripts/contract_delta.py snapshot # обновить baseline после осознанного изменения контракта
uv run python scripts/demo_data.py seed          # демо-витрина в data/demo.db (реальная БД не трогается)
uv run spendtrack anonymize file.csv [out.csv] [--rows N] [--anon-column "ФИО"]  # обезличить образец (dev: scripts/anonymize.py)
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

## Бэкапы: локальный + offsite (#12, K2)
- `spendtrack backup [--keep N] [--copy-to ПАПКА] [--force]` (логика — `spendtrack/backup.py`,
  dev-обёртка `scripts/backup.py`): локальный снимок `VACUUM INTO` (`data/backup/spend-<UTC>.db`,
  ротация `--keep`, дефолт 14) + опциональная внешняя копия. Путь БД — `SPENDTRACK_DB_PATH` →
  `data/` репо → user-data (`resolve_data_dir()`; доступно установкам через `uv tool`).
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

## Правки полного аудита 24.09 (claude-opus-5)

- **Даты/месяцы (P0):** `store.valid_month()`; `_resolve_month` устойчив (явный месяц → MAX(date) → текущий);
  `csv_import._iso_date` понимает `YYYY/MM/DD` и `YYYY.MM.DD`, нераспознанная дата → `_skip: date_unrecognized`
  (мусор в `date` ломал `/` и `/dashboard`); `?month=x`: страницы игнорируют, `/api/budgets` → 422, экспорт — дефолт.
- **Очередь:** `approve_all_reviews(..., known=…)` — whitelist таксономии (предложение LLM вне таксономии → `other`).
- **Create:** `TxIn` валидирует `amount`/`date` → 422; htmx-ответ экранирует описание (`escape`).
- **TOML:** `_dump` сохраняет `display_name`; `delete_category` чистит `merchant_cache`/`examples`.
- **LLM:** `parse_llm_json` принимает только dict; `merchant: null` безопасен.
- **Импорт:** `add_batch(commit=False)` (партия атомарна с партией строк); JSON-тело с `Content-Length` > 2×лимита → 413.
- **Эксплуатация:** `/health/data` — TTL-кэш 10 с + `?fresh=1`; Origin сверяется с фактическим `Host`.
- **Промпт:** few-shot примеры с одиночными скобками (`{{...}}` путали модель).
- **Отложено:** двухфазный импорт при LLM (write-lock), быстрый путь `Store.__init__` по `user_version`,
  сноска про исключённые не-RUB операции, simplify-проход.

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
- **Property-based и chaos (§G, 25.09):** `tests/test_property_parsers.py` (hypothesis: любой ввод →
  валидная запись или `_skip` с известной причиной; даты в БД только ISO) и `tests/test_import_chaos.py`
  (CR в поле, CRLF/cp1251/битые байты, 20K-описание, лимит, пустышки, случайные байты, параллельная
  UI-запись). Найдены и закрыты: падение csv-парсера на одиночном `\r` (нормализация переводов строк в
  `import_csv`/`anonymize_csv`) и `parse_amount("nan"/"inf")` → контролируемая `InvalidOperation`
  (CLI `add` — exit 1). Фикстуры миграций v3/v4 — `tests/test_migrations.py`.

## Golden-набор мерчантов (§G-4)
- `tests/golden/merchants.csv` (`description,expected_category,bank`) — курируемые реалистичные формулировки;
  строки без ожидания (пустой `expected_category`) держат метрику «нерешённых» живой.
- `scripts/golden_report.py` (не тест-гейт, read-only): `rule_hit_share`, `misclassified`, `unresolved`,
  `surprise` → `reports/golden.json`. База 25.09 (синтетика): **34/34 rule-хитов, 6/40 нерешённых, 0 ошибок**.
  Основа калибровки порога 0.9 на реальных фикстурах (K4): набор расширяется без кода.
- Тест `tests/test_golden_report.py`: контракт метрик (чистая функция, стаб) + консистентность набора
  (слаги таксономии; 0 ошибок/сюрпризов; ≥5 нерешённых).
- Битый JSON-конверт: не-JSON/не-UTF-8 тело → 400, неполные поля → 422 (`_json_payload` в `api.py`;
  live-смоук 21.09 вскрыл 500 на кривой кодировке) — и `/api/import`, и `/api/transactions`.
- **Реальные форматы (подтверждены публичными первоисточниками 23.09, `RESEARCH_BANK_STATEMENT_SAMPLES.md`):**
  Сбер email-CSV («выписка на e-mail как Excel-лист»: `Тип карты;Номер карты;Дата совершения операции;…;
  Сумма в валюте счета`; `;`, utf-8, даты `%d.%m.%Y`, суммы с запятой, edge `-,01`) и Т-Банк (13 колонок:
  `Дата операции;…;Статус;…;MCC;Описание;Бонусы`; `;`, cp1251, проведённые — `Статус=OK`). Адаптеры научены
  этим колонкам; `sniff_bank` различает Т-Банк по MCC/кэшбэк/бонусы (раньше реальный Т-Банк опознавался как
  Сбер и импортировался случайно). Golden-shape синтетика — `tests/synth_bank.py: gen_sber_email/gen_tinkoff_real`.
- **Сбер XLS/XLSX у физлиц не существует** (редизайн СберБанк Онлайн 2021 → PDF; «Excel-лист» по e-mail —
  это CSV) — Excel только у бизнес-API, структура листа публично не описана; #4 остаётся data-gated.
- **ЮMoney CSV кошелька публично не подтверждён** (выписка — PDF, API — JSON `operation-history`) —
  yandex-адаптер best-effort.
- `missing_columns` возвращает группу синонимов через « / » (у банка бывает несколько форматов).
- **Атомарность партии (фикс 23.09, ресёрч слабых слоёв):** `pseudonymize` / `merchant_cache_set` /
  LLM-кэш мерчанта больше не коммитят внутри батча (`commit=False`; сквозной параметр в
  `categorize_transaction`/`classify_with_injectable`), rollback при сбое в середине откатывает
  и строки, и псевдонимы счетов; кастомный `classify` обязан сам использовать `commit=False`.
  Регресс — `tests/test_csv_import.py`, `test_store_helpers.py`, `test_categorize.py`.
- **CLI-импорт:** файл читается как `bytes` (работает cp1251-фолбэк `import_csv`, паритет с API/UI)
  и передаёт реальное имя файла в партию (`import_csv(..., filename=…)` → `import_batches.filename`).
- **Форма `POST /api/transactions` без обязательного поля:** 422 (общий хелпер `_validation_422`),
  а не 500 — паритет с JSON-веткой.

## Anonymizer выписок (P1 #3, K2)
- `spendtrack anonymize выписка.csv [образец.csv] [--rows N] [--anon-column "ФИО"]` (логика —
  `spendtrack/anonymize.py`, dev-обёртка `scripts/anonymize.py`): описания/мерчанты →
  `ОПЕРАЦИЯ_0001`, карты/счета → `КАРТА_0001`, номера документов → порядковый номер; шапка, порядок строк,
  даты, суммы, статусы, разделитель и CRLF сохраняются — образец остаётся валидной фикстурой для адаптеров.
  Колонки определяются по синонимам (`DESC_ALIASES`/`ACCOUNT_ALIASES`/`DOC_ALIASES`); нераспознанные
  не трогаются и перечисляются в отчёте («проверьте, нет ли личных данных»). Вход utf-8/cp1251, выход utf-8.
  Даты/суммы/категории не обезличиваются: stderr-предупреждение, по умолчанию остаются первые 5 строк
  (`--rows 0` — все; для dev-фикстур указывать явно). Запись — bytes (text-mode Windows удвоил бы «\r»).
  Тесты: `tests/test_anonymize.py` (в т.ч. «обезличенный образец импортируется с теми же датами/суммами»,
  лимит строк, CRLF без удвоения, варнинг/ошибки CLI).

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
- **Порядок и подача на дашборде (M-5, дизайн-ревью):** аномалии — отдельная карточка `#anomalies-card`
  ПЕРВЫМ блоком (иконка типа, мерчант + деталь, сумма справа, «Открыть» → список с `q=<мерчант>`);
  в карточке дайджеста подсекции аномалий больше нет. Дельты расходов — словами `delta_words()`
  («↑ на 6 925,00 ₽» / «↓ на …» / «без изменений»; рост трат — ↑, красный), знак «Δ» убран. Бюджеты —
  по риску (`budgets_progress` сортирует по pct desc, tie-break по имени) + маркер темпа: вертикальная
  риска на баре = `_month_elapsed_pct()` (доля прошедшего месяца; прошлый — 100, будущий — 0; легенда
  «риска — прошло N% месяца»). «Это ок» для аномалий не делаем: дайджест read-only, без состояния.
  Тесты: `test_ui_polish.py` (карточка/порядок/маркер/Δ), `test_amounts.py:delta_words`,
  `test_budgets.py:sorted_by_risk`, e2e `test_dashboard_digest_card` (аномалии — своя карточка).

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
- Фрейм платного блока — **«разовая поддержка разработки»** (тяжёлое ревью 21.09): managed-LLM-прокси и
  «разовая лицензия» убраны из landing/README/FUNDING-окрестностей как несуществующие/противоречащие AGPLv3;
  у Сбера — честная оговорка (у физлиц выписка — PDF, CSV по e-mail и не у всех; XLS/XLSX у физлиц
  не существует — ресёрч образцов 23.09, обещание «XLS-импорт в планах» убрано). Юр-природа — услуги (оферта).
- Деплой: `.github/workflows/pages.yml` при push в `main` с изменениями в `landing/**` (source — GitHub Actions;
  Pages включён через `gh api repos/ExNihil14/spend-tracker/pages -X POST -f build_type=workflow`).
  URL — <https://exnihil14.github.io/spend-tracker/>.
- **Порядок секций и финальный CTA (M-8, дизайн-ревью):** hero → facts → **«Что вы увидите»** (3 кадра
  пути: импорт → очередь → дайджест, `#screens`) → **privacy** (дифференциатор — ДО установки) → install →
  features → «LLM предлагает, вы решаете» (без дубля скриншота) → demo → support → FAQ → roadmap →
  **финальный CTA** (`class="final-cta"`: команда установки + демо) → EN. Формулировки фич/facts «с результата»
  («Выписки без ручной правки», «Категории расставляются сами», «Загрузили дважды — дублей нет»,
  «ИИ выключен, пока вы сами не включите»). Скриншоты пересняты после M-4…M-7 (`shot-import/approve/digest/
  dashboard`, 2x; скрипт — temp `recapture_m_waves_shots.py`, стенд 8767). Сетки — `minmax(0, 1fr)`
  (фикс горизонтального скролла на 1280px: `.steps/.grid3/.screens/.facts .wrap` + `min-width:0` у `.step/.cmd`).
- Локальный предпросмотр: `python -m http.server 8788 --directory landing` → <http://127.0.0.1:8788/>.
- Скриншоты для лендинга снимаются со стенда демо-данных (`scripts/demo_data.py seed` + сервер 8767).
- Перед запуском включить кнопку Boosty (сейчас выключена во всех трёх местах): `landing/index.html`
  (disabled-кнопка), `README.md` и `.github/FUNDING.yml` (закомментированный `custom`) — вставить реальный URL.
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

## Список: фильтры, ссылки категорий, чарты (смоук 23.09)
- **Фильтр категории/поиска в «Сначала новые» (регресс-фикс):** `list_transactions_days` выбирал дни по
  условию, но строки — `WHERE date IN (...)` без фильтров → в таблицу протекали все операции этих дней.
  Теперь фильтры применяются и к выбору строк; регресс-тесты — `tests/test_tx_paging.py`.
- **Клик по бейджу категории** — полная навигация (`hx-boost="false"`) и **месяц в href**
  (`/?month=YYYY-MM&category=…`): иначе htmx наследует `target/select/swap` от `#tx-table` и подменяет
  только таблицу (шапка/итоги/фильтр остаются от прошлого состояния), а без месяца уводит в последний месяц.
  То же — ссылки топ-категорий на дашборде; «✕» сброса фильтров сохраняет месяц; селект фильтра — RU-имена.
- **Чарты дашборда:** подписи — `display_name` категорий (`categories_json[*].label`), цвета — из
  semantic-токенов через CSS-переменные (`dashboard.js` читает `--accent-bg/--fg/--fg-muted`), цвета
  категорий — по слагу (`cat_colors`). Тест: `tests/test_ui_polish.py::test_dashboard_chart_data_has_display_labels`.

## Токены и цвет-семантика (дизайн-ревью, M-1/M-3)
- `src/spendtrack/tokens.css` — 2 слоя (primitives → semantic); приложение подключает через Tailwind v4
  (`tailwind.css`: `@import` + `@theme inline` → утилиты `bg-surface`, `text-fg-muted`, `border-line`,
  `bg-accent-bg`, `text-income/warn/danger`); лендинг — `landing/tokens.css` (копия; синхронность проверяет
  `tests/test_landing.py::test_tokens_copy_in_sync`).
- **В разметке — только semantic-классы** (прямой палитры Tailwind нет; проверяется grep'ом при ревью).
- Семантика цвета: расходы — нейтральный `text-fg` со знаком «−» (красный только перерасход/аномалии/
  деструктив); доход — `text-income`; один primary-акцент на экран (`bg-accent-bg`); «Одобрить все»/
  «Проверить» — secondary (границы), «Удалить» — ghost (danger только на hover); ссылки/фокус — `accent`.
- После правок токенов/классов — пересборка CSS: `uv run python scripts/build_css.py` (CI: `--check`).

## Числа, язык и категории в UI (дизайн-ревью, M-2)
- **Денежная форма** — `fmt_money(kopecks, currency='RUB', signed=True)` → «−155 365,18 ₽» (NBSP-разряды,
  запятая, ₽/код валюты; `signed=False` для лимитов/бюджетов — без «+»). Подписи: `fmt_month('2026-09') →
  «Сентябрь 2026»`, `fmt_date('2026-09-13') → «13.09»` (таблицы; ISO — только экспорт/API/URL).
  Машинные формы (`fmt_amount`, ISO-даты) не тронуты — CSV/промпты/CLI/keyset-пагинация.
- **Категории**: `taxonomy.toml` получил `display_name` (RU) для всех 18; в UI рендерится `catname(slug)`
  (слаг — ключ БД/URL/API, RU-имя — только отображение; неизвестный слаг показывается как есть).
- Аномалия `near_duplicate` в UI/CLI-дайджесте называется «возможный дубль»; детали аномалий — в `fmt_money`.

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
- **Безопасный bulk и клавиатура очереди (M-4, дизайн-ревью):** кнопка «Одобрить все с уверенностью ≥ 60% (N)»
  (порог в `partials/approve_all.html`; при 0 уверенных кнопки нет; `hx-confirm` называет число и предупреждает,
  что слабые останутся). Endpoint `/api/reviews/approve-all` принимает `min_confidence` 0..1 (иначе 422);
  без параметра — вся очередь (API-совместимость). Уверенность — `conf_level()` («низкая/средняя/высокая»,
  границы 0.5/0.7) + мини-бар с `aria-label`; предложение LLM подсвечено в самом select («— предложено»),
  дубль-чип убран; «Пропустить» — текстовая ссылка. Клавиатура: `static/approve.js` (`j/k`, `Enter`, `s`,
  `1–9`; фокус на реальной кнопке строки, после свопа — та же позиция, выбранная строка `.is-selected`).
  Тесты: `tests/test_review_queue.py` (порог/уровни/разметка), e2e `test_approve_all_button` +
  `test_approve_keyboard_triage`; QA-план — `spec/QA_APPROVE_SMOKE.md` TC-08/16/17/18.
- Тесты: `tests/test_ui_polish.py` + `test_colors.py` + дополнения `test_amounts.py`/`test_digest.py`
  (знаки аномалий: медианы хранятся магнитудами — знак расхода ставится явно); e2e
  `tests/e2e/test_ui_polish_e2e.py`. Источник формулировок — `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` §4/§6.

## Главная: данные выше форм (M-6, дизайн-ревью)
- Итоги месяца — строкой (`Доход/Расход/Баланс` + стрелки месяцев), а не четырьмя KPI-карточками (на дашборде
  карточки остались — дубль сжат на одной из страниц).
- Формы «Импорт CSV» и «Добавить» свёрнуты в кнопки шапки таблицы транзакций (`[data-toggle]` →
  панели `#import-panel`/`#add-panel`, по умолчанию `hidden`; `aria-expanded`/`aria-controls` — в `app.js`;
  ссылки `/#import`, `/#add` (лендинг, чек-лист, дашборд) открывают панель через hash-обработчик).
- Импорт: `<input type=file>` + drop-zone (`#import-drop`, drag&drop в `app.js` подставляет файл в input),
  textarea осталась запасным путём; форма `hx-encoding="multipart/form-data"`. API `/api/import` принимает
  JSON | form | multipart: файл читается байтами (utf-8-sig/cp1251-фолбэк внутри `import_csv`), имя файла —
  источник партии; пустой `file` (filename="") → фолбэк на textarea.
- Тесты: `test_api.py` (multipart utf-8/cp1251/пустой файл), `test_ui_polish.py` (структура/скрытые панели/
  drop-zone/итоги строкой), e2e `open_panel()`-хелпер + `test_import_csv_by_file_upload`.

## Навигация, /settings и типографика (M-7, дизайн-ревью)
- **Nav:** пункты приглушены (`text-fg-muted`), активный — `text-fg-strong` + подчёркивание 2px accent
  (`underline decoration-accent decoration-2 underline-offset-4`); активность по `request.url.path`
  (`/` — точное совпадение, остальные `startswith`) в `base.html`.
- **Типографика (P1-5):** UPPERCASE остался только у заголовков колонок (`thead tr`, 12px tracking);
  заголовки карточек — sentence case 15px/600 (`text-[15px] font-semibold`); мелкие подписи (KPI-карточки,
  тестер, «Переименовать:») без uppercase. Исключения: паттерн правила (моно-инпут — намеренно uppercase),
  заголовок-дата в `tx_rows` (только цифры).
- **/settings — автосохранение:** цвет категории и лимит бюджета сохраняются по `change` (`hx-trigger="change"`,
  кнопки «OK» убраны); ответ — фрагмент + OOB-тост «Сохранено» (`spendtrack/ui.py: oob_toast`, общий с api.py;
  заодно тост переведён с палитры slate на токены). У «Удалить» у занятой категории `disabled`
  + `title="Используется (N) — сначала перенесите операции в другую категорию"`.
- Тесты: `test_settings.py` (форма без OK/тост/title), `test_ui_polish.py` (активный пункт nav + `aria-current`,
  sentence case), e2e (бюджет — **Enter/change-автосейв**, цвет — change → тост).
- **Правки по тяжёлому ревью 24.09 (Opus-5, адъюдикация в `EXPERT_REVIEW_M_WAVES_HEAVY_OPUS5_2026-09-24.md`):**
  бюджетная форма `hx-trigger="change, submit"` (Enter не уходит в нативный GET); drop-zone — window-preventDefault
  + счётчик входов; approve.js сбрасывает клавиатурный режим по pointerdown вне очереди; легенда бюджетов
  «отметка темпа: прошло X% месяца», маркер — только для текущего месяца; ссылка аномалии — с `month=<месяц аномалии>`;
  nav `aria-current="page"`; тест «тот же CSV, другое имя → 0 добавлено» (fingerprint без имени файла).

## Первый запуск: чек-лист 4 шага (P2 #10)
- Главная при `first_run` (нет транзакций И нет партий импорта) показывает `#start-checklist`
  (`partials/start_checklist.html`): 4 шага со ссылками (#import/#add, /approve, /settings, /dashboard) +
  `/help#quick-start`. Состояние серверное (`Store.counts()` + `Store.batch_count()`), localStorage не нужен;
  после первых данных (импорт или ручное добавление) чек-лист исчезает — не навязывается активному пользователю.
- Тесты: `tests/test_ui_polish.py` (3: показ 4 шагов со ссылками; скрытие после партии импорта; после ручного add)
  + e2e `test_first_run_checklist_visible_then_hidden` (виден на пустой БД, скрыт после данных).
  Попутно e2e-`clean_db` чистит `import_batches` — состояние партий не течёт между session-scoped тестами.

## Периметр, lifecycle и supply chain (security-пасс, 22.09)
- **Периметр браузера**: `spendtrack/security.py` (`origin_allowed`, `trusted_hosts`, `content_security_policy`)
  + middleware `_origin_guard`/`_security_headers` в `main.py`: state-changing запросы с чужим
  `Origin`/`Sec-Fetch-Site` → 403; без заголовков (CLI/TestClient) — пропуск. `TrustedHostMiddleware` →
  400 на чужой Host (DNS-rebinding). **Codespaces**: при `CODESPACES=true` trusted hosts/Origin/frame-ancestors
  расширяются доменом форвардинга (`GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN`, обычно `app.github.dev`) —
  прокси сохраняет публичный Host; домен GitHub-контролируемый. Тесты: `tests/test_security_perimeter.py`.
  CSRF-токены осознанно не вводим (нет сессии/cookie).
- **Lifecycle SQLite**: `deps.get_store()` — FastAPI dependency с `yield`: одно соединение на запрос,
  `close()` гарантирован (раньше — GC), `PRAGMA optimize` перед закрытием, `cache_size=-8000`,
  `temp_store=MEMORY`; `check_same_thread=False` (sync-роуты в threadpool). Роутеры принимают
  `store: Annotated[Store, Depends(get_store)]`. Замеры bench.py: без регресса (месячные агрегаты 4.7→0.8 мс,
  `/dashboard` 50K 388→344 мс — кэш страниц; import в пределах шума).
- **Supply chain (A03:2025)**: `uv lock --check` + `pip-audit --skip-editable` (dev-зависимость) в CI-lint;
  `.github/dependabot.yml` (pip + github-actions, weekly); все actions пиннуты по commit SHA с комментарием
  версии; `permissions: contents: read`.
- **Диск**: BitLocker + NTFS-ACL на `data/` — пункт чек-листа юзера (на текущей машине BitLocker выключен);
  offsite-копия — plaintext, при выносе шифровать архив. SQLCipher — осознанно нет.

## CSS-сборка (prebuilt Tailwind, кроссбраузерность-пасс 21.09)
- В проде отдаётся готовый CSS `src/spendtrack/static/app.css` (~70 КБ); browser build (Play CDN, 282 КБ JS,
  dev-only) удалён. Вход — `src/spendtrack/tailwind.css` (`@import "tailwindcss"; @source "./templates";`).
- Сборка/проверка: `uv run python scripts/build_css.py` / `--check` (в CI-джобе lint). CLI — официальный
  standalone-бинарник Tailwind v4.3.3, пин версии + sha256, без Node (`D:/dev/tools/tailwindcss/`).
- **После правок классов в шаблонах — пересобрать CSS** (иначе новых утилит не будет); `--check` в CI ловит
  отсутствие артефакта/ключевых селекторов, e2e-смоук — визуальную регрессию.
- Кросс-браузерный смоук: `tests/e2e/test_crossbrowser_smoke.py` (рендер без ошибок консоли, отсутствие
  горизонтального скролла на 320px — WCAG 1.4.10, axe **critical+serious = 0**). В CI: chromium — полный e2e,
  firefox+webkit — только этот файл (`--browser firefox --browser webkit`).
- Таблицы обёрнуты в `.table-scroll` (`role="region"`, `tabindex="0"`, sticky `<thead>`, edge-тени);
  навбар — `flex-wrap`. Матрица поддержки — README «Поддерживаемые браузеры».
- Фаза 2 (контрасты/доступность): muted-текст `slate-400` (4.5:1), кнопки `emerald-700`/`amber-700`,
  `p a, li a` — подчёркивание (1.4.1); date-хинт `ГГГГ-ММ-ДД` с `aria-describedby` (Safari); у sentinel
  догрузки — кнопка «Показать ещё» (`hx-trigger="revealed, click"`; в UI дремлет — страница = месяц,
  активируется в многомесячном режиме).
- Фаза 2 (оптимизация, 22.09): **Chart.js грузится только на дашборде** — `base.html` даёт блок `scripts`,
  `dashboard.html` подключает `dashboard.js`, который динамически тянет `chart.umd.min.js` (URL из
  `data-chart-src`); на остальных страницах 205 КБ не запрашиваются (e2e-тест
  `test_chart_js_loads_only_on_dashboard`). **Версия статики**: `assets.static_url()` → `/static/<файл>?v=<sha8>`
  (Jinja-хелпер `static`), middleware ставит `Cache-Control: immutable` для `?v=`, `no-cache` без версии,
  `no-store` для HTML/API (тесты `tests/test_static_cache.py`).
- Заголовки безопасности: CSP + `nosniff` + `Referrer-Policy: no-referrer` (middleware `main.py`,
  тесты `tests/test_security_headers.py`). С 22.09 `script-src 'self'` (без `unsafe-*`): inline-скрипты и
  `hx-on::*` вынесены в `/static/app.js` и `/static/dashboard.js` (данные графиков — в `#dashboard-data`
  data-атрибутами), `htmx.config.allowEval=false`. `style-src 'unsafe-inline'` — осознанно (inline-стили
  цветов/темы). Подробности — `SECURITY.md`.

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
uv run --with coverage coverage run -m pytest -q && uv run --with coverage coverage report --include="src/spendtrack/*"
                                # замер покрытия (без постоянной зависимости); сейчас src ~96%
```
**Стратегия и организация тестов — `spec/TESTING.md`** (уровни/маркеры, принципы, как добавлять, анти-скоуп).
Аудит тестирования и функциональности (QA-лид, 23.09): `D:\dev\docs\machine\AUDIT_TESTING_SPENDTRACKER.md`
(покрытие по модулям, матрица «функция→тесты→пробел», P0/P1/P2; P0 закрыт — 499 unit, покрытие 96%).
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