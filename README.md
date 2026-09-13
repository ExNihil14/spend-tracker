# Spendtrack

Трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx, offline-first.

## Установка (чистая машина)

```bash
git clone https://github.com/ExNihil14/spend-tracker.git
cd spend-tracker
uv sync                        # создаёт .venv и ставит зависимости
```

## Настройка

```bash
cp .env.example .env.local      # заполни ключи (необязательно для работы)
```

`SPENDTRACK_FREEL_LLM_API_KEY` — для LLM-категоризации. Без него трекер работает, но правила вручную.

## Запуск

**Вариант 1 — скрипт (рекомендуется, проверяет порт):**
```powershell
.\run.ps1
```

**Вариант 2 — вручную:**
```bash
uv run uvicorn spendtrack.main:app --host 127.0.0.1 --port 8766
```

Открой http://127.0.0.1:8766

## CLI

```bash
uv run python -m spendtrack.cli add -23.45 "milk"          # добавить расход
uv run python -m spendtrack.cli import file.csv --bank auto  # импорт CSV
uv run python -m spendtrack.cli report                       # отчёт по категориям
uv run python -m spendtrack.cli count                        # количество записей
```

## Автозапуск (Task Scheduler)

- Задача: запуск при входе пользователя
- **Start in:** `D:\dev\personal\spend-tracker` (важно: старт после монтирования D:)
- **restart on failure:** 3 раза (по 1 мин)
- **Убрать** «stop if runs longer than 72 hours» (иначе ночью убьёт сервер)
- **Задержка 30 сек** перед стартом (ждём D:)
- Триггер: «at log on» → delay 30s
- Команда: `powershell -NoProfile -ExecutionPolicy Bypass -File D:\dev\personal\spend-tracker\run.ps1 -NoReuse`

## Бэкап БД

`VACUUM INTO` с WAL. Бэкап через `sqlite3` online backup или копировать `data/spend.db` только **на холодную** (когда нет записи). НЕ копировать `.db` без `-wal`/`-shm`.

## Стек

- **Backend:** FastAPI + SQLite (WAL)
- **Frontend:** htmx + Tailwind CSS + Chart.js
- **LLM:** OpenRouter `:free` / Abacus DeepSeek (категоризация, 0 кредитов)
- **Тесты:** pytest (44), ruff (линтер)

## Лицензия

Личный проект. MIT.