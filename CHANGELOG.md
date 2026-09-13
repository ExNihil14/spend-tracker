# Changelog

Все заметные изменения проекта — по версиям. Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — SemVer.

## [0.1.0] — 2026-09-14

Первая зафиксированная версия: ядро трекера работает, UI готов к реальному использованию.

### Added

- Ядро: SQLite-хранилище (WAL), fingerprint-дедупликация импорта, LLM-категоризация с фолбэками (FreeLLMAPI → OpenRouter → DeepSeek через abacus-web → оффлайн-правила), CSV-импорт с адаптерами банков, отчеты по категориям, CLI.
- API: FastAPI, JSON + form-urlencoded, HX-ветка для htmx; эндпоинты транзакций, категорий, экспорта, pending-count.
- UI: htmx + Tailwind, списки с фильтрами по URL (hx-push-url), дашборды Chart.js, форма добавления, индикаторы.
- Качество: 44 теста pytest (оффлайн, без LLM), perf-маркер с JSON-отчетом, ruff clean.
- Окружение: uv/pyproject, .env.example, git trunk-based, публичный GitHub main с защитой.

### Changed

- Переход с TemplateResponse на контекст-локальное окружение для htmx (3.x совместимость).
- Модельный роутинг: OpenRouter `:free` как основной agentic-канал; abacus-web DeepSeek для анализа.

### Removed

- Секреты из .env.example (значения заменены пустыми/плейсхолдерами).

### Security

- Проверка git-истории перед публикацией на секреты; данные (`data/`) и ключи вне git.