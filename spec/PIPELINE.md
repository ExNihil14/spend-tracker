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
```

## Doctor (целостность данных)
- CLI `spendtrack doctor` — таблица чеков; `--json` — машинный JSON; exit 0 = ok/warn, 1 = critical.
- API `GET /health/data` → `{status, checks:[{id, severity, count, detail}]}`; 503 при critical.
  `GET /health` (liveness) — отдельный эндпоинт, не трогать.
- Проверки: quick_check (critical) · дубли fingerprint (critical) · `user_version==SCHEMA_VERSION` (critical) ·
  категории вне таксономии (`transactions.category` critical; `category_llm` warn только при
  `source != 'llm_pending_review'`; rules/budgets/merchant_cache/examples warn) · pending с чужим source (warn) ·
  пустые import_batches (info) · бэкап `data/backup/spend-*.db` (папки нет → info, >48ч → warn, quick_check → critical).
  Битая БД не роняет прогон: упавший чек становится critical (`db_open`/`не удалось выполнить проверку`).
- Авторемонта нет (read-only; Store на входе до-мигрирует старую схему — это норма).
- История (16.09): doctor нашёл, что задача `spendtrack-backup` не срабатывает (0x800710E0: Principal Interactive +
  `DisallowStartIfOnBatteries=True` + `StartWhenAvailable=False`). Починено: догон пропусков включён, запуск на батарее
  разрешён, `ExecutionTimeLimit=PT1H`; прогон задачи → `LastTaskResult=0`, свежий бэкап, doctor = ok.
  Остаётся осознанно: `LogonType=Interactive` (при пропуске 03:00 задача догоняется при следующем входе в систему).

## Тесты / анализ
```bash
uv run pytest -q                # 180 unit (e2e отдельно: uv run pytest tests/e2e -m e2e), все оффлайн (LLM-стаб)
uv run ruff check               # lint, чистый
```
Правила Фазы 2 (контур верификации):
- Commit ПЕРЕД началом задачи, diff ПОСЛЕ.
- Визуальная проверка в браузере для ЛЮБОГО UI-изменения (не только pytest).
- Smoke-тест полного сценария обязателен: POST /transactions (live LLM) → GET / (htmx-отображение).

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