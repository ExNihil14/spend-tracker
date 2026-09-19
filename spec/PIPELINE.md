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
uv run spendtrack doctor [--json]                # целостность данных (exit 1 только на critical)
uv run spendtrack recurring [--json]             # детекция рекуррингов/подписок
uv run spendtrack suggest-rules [--json]         # подсказки keyword-правил из правок (read-only)
uv run spendtrack digest [--days N] [--json]     # дайджест недели + флаги аномалий (read-only)
uv run python -m scripts.restore_drill           # restore-drill последнего бэкапа → маркер для doctor
```

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

## Тесты / анализ
```bash
uv run pytest -q                # 252 unit (e2e отдельно: uv run pytest tests/e2e -m e2e), все оффлайн (LLM-стаб)
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
1. OpenRouter :free (nemotron-super-120b) — primary (канон: `spec/ARCHITECTURE.md` §LLM-маршрут).
2. OpenRouter :free (nemotron-3-super-120b) — fallback.
3. abacus-web shim 127.0.0.1:3201 (deepseek-v4-1-flash) — deepseek, токен TTL 1ч.
4. Офлайн-правила/кэш — без сети.

## Правило
- Отчёт агента не принимается без проверки по логам/живому ответу (не «галлюцинировать готово»).