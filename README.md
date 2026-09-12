# Spendtrack

Трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx, offline-first.

## Запуск
```powershell
.\run.ps1          # проверяет порт 8766, при занятом открывает браузер
uv run uvicorn spendtrack.main:app --host 127.0.0.1 --port 8766
```
CLI: `uv run python -m spendtrack.cli add -23.45 "milk"` / `report` / `import file.csv --bank auto` / `count`

## Автозапуск через Планировщик задач (проверено ревью, надо применить)
- Задача: запуск при входе пользователя, **Start in = `D:\dev\personal\spend-tracker`** (важно: старт после монтирования D:, иначе uv не найдёт venv)
- **restart on failure = 3 раза** (по 1 мин), **УБРАТЬ «stop if runs longer than 72 hours»** (иначе ночью убьёт сервер без причины)
- **Задержка 30 секунд** перед стартом (ждём D:) — в триггере «at log on» → delay 30s
- Команда: `powershell -NoProfile -ExecutionPolicy Bypass -File D:\dev\personal\spend-tracker\run.ps1 -NoReuse`

## Бэкап БД
- `VACUUM INTO` гоняется с WAL — делать бэкап через `sqlite3` online backup или копировать `data/spend.db` только «на холодную» (когда нет записи). НЕ копировать файл ВАРХОТАН ДЛЯ WAL-режима (нельзя копировать только `.db` без `-wal`/`-shm`).