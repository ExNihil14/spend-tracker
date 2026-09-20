# Spendtrack

[![CI](https://github.com/ExNihil14/spend-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/ExNihil14/spend-tracker/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ExNihil14/spend-tracker)

Трекер личных расходов с LLM-категоризацией: детерминированное ядро (правила) закрывает большую часть транзакций,
LLM подключается только для остатка, спорное уходит в очередь ручного подтверждения. FastAPI + SQLite + htmx,
offline-first: без ключей и сети работает на правилах.

![Список транзакций](assets/screenshot-transactions.png)

## Для кого

Локальный трекер для тех, кто **не отдаёт банковские данные в облако** и готов раз в месяц закинуть CSV-выписку:

- **Подходит:** пользователи выписок Сбер/Тинькофф/Яндекс; privacy-минималисты и self-hosted-аудитория; те, кому нужны
  бюджеты, автодетект подписок и недельный отчёт об аномалиях — без подписки и bank-API.
- **Не подходит:** тем, кто ждёт автоматический bank sync и приложение из App Store; семьям с общим бюджетом
  (мультиюзера нет); учёту инвестиций и мультивалютным портфелям (в планах нет).

## Возможности

- **Импорт выписок** Сбера, Тинькофф и Яндекса с автоопределением формата; дедуп по fingerprint — повторный импорт ничего не добавляет.
- **Каскад категоризации:** кэш мерчантов → keyword-правила (first-match) → LLM → офлайн-правила. Автоприём при `confidence ≥ 0.9`, остальное — в очередь «Подтвердить».
- **Очередь подтверждения** с diff «предложение LLM / ваша категория»; одобренная правка учит кэш мерчантов и few-shot.
- **Управление таксономией в UI** (`/settings`): категории, правила с приоритетом (↑/↓), диагностика «мёртвых» и дублирующих правил, переименование категории с миграцией данных, тестер описаний.
- **Дашборд**: расходы по дням и категориям; фильтры и сортировки живут в URL.
- **Экспорт CSV/Excel**: выгрузка всех транзакций или текущего фильтра — данные всегда можно забрать с собой
  (CSV открывается в Excel, XLSX — с нативными датами/числами).
- **CLI** для быстрых операций и калибровки порога авто-приёма по фактическим исходам.

## Быстрый старт

Нужны Python 3.13+ и [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ExNihil14/spend-tracker.git
cd spend-tracker
uv sync
cp .env.example .env      # необязательно: LLM — свой ключ/Ollama или free-каналы (см. «Настройка»)
```

Запуск:

```powershell
.\run.ps1                  # Windows: проверит порт и откроет браузер
```

```bash
uv run uvicorn spendtrack.main:app --host 127.0.0.1 --port 8766
```

Приложение: <http://127.0.0.1:8766> — БД создастся сама в `data/spend.db`.

## Демо-режим (витрина за минуту)

Синтетические данные (~5 месяцев): все фичи видны сразу — подписки, дайджест с аномалиями, бюджеты
(перерасход и ~80%), очередь подтверждения, правки/примеры и кандидаты правил.

```bash
uv run python scripts/demo_data.py seed     # data/demo.db (реальная БД не трогается)
uv run python scripts/demo_data.py status   # что засеяно + счётчики фич
uv run python scripts/demo_data.py clean    # убрать демо по манифесту
# стенд на отдельной БД:
SPENDTRACK_DB_PATH=data/demo.db uv run uvicorn spendtrack.main:app --port 8767
```

В Codespaces демо-данные засеиваются автоматически при первом старте в `data/demo.db`, и сервер обслуживает
именно её (подписки, дайджест с аномалиями, бюджеты и очередь видны сразу).

## Тестирование в GitHub Codespaces

Прямая ссылка: [создать codespace](https://codespaces.new/ExNihil14/spend-tracker) (квота GitHub Free: 120 core-часов/мес).
Контейнер сам ставит `uv`, зависимости и запускает приложение на порту 8766; порт **приватный** — доступен только
после входа в GitHub (в приложении нет своей авторизации). Данные — **только синтетические**:

```bash
# демо-строки для проверки очереди /approve — в ту же БД, что обслуживает сервер:
SPENDTRACK_DB_PATH=data/demo.db uv run python scripts/review_demo.py seed
```

Открыть приложение: вкладка **PORTS** → порт 8766 → значок «Open in Browser».
Сервер стартует автоматически при подключении к codespace (`.devcontainer/start-app.sh`); если не поднялся —
`bash .devcontainer/start-app.sh`, состояние в `tail -f /tmp/spendtrack.log`.
Если после обновления кода страница отдаёт 500, а код уже новый — работает старый процесс
(шаблоны Jinja горячие, Python — нет): `pkill -f "uvicorn spendtrack" && bash .devcontainer/start-app.sh`
(или Codespaces: Stop/Start). Дальше сервер сам подхватывает изменения (`--reload`).
Кнопка e2e-тестов в облаке (опционально): `uv run playwright install --with-deps chromium`.

## Использование

- `/` — транзакции: импорт CSV, добавление, поиск, фильтры по месяцу и категории, сортировки, дневные итоги.
- `/dashboard` — графики и итоги по категориям.
- `/approve` — очередь подтверждения категорий.
- `/settings` — категории, правила, тестер описаний.

![Дашборд](assets/screenshot-dashboard.png)

### CLI

```bash
uv run spendtrack add -23.45 "milk"           # добавить расход (категория — из каскада правил/LLM)
uv run spendtrack import statement.csv --bank auto
uv run spendtrack report --month 2026-09
uv run spendtrack count
uv run spendtrack confidence                  # калибровка порога авто-приёма (бакеты, покрытие, ошибки)
uv run spendtrack llm-status                  # режим LLM: off/byo/ollama/free (без сети и ключей)
uv run spendtrack export --format csv         # выгрузка транзакций (csv|xlsx, --month/--from/--to, --out)
```

## Настройка

- `config/settings.toml` — порт, эндпоинты free-цепочки, модель Ollama, порог авто-приёма (`acceptance.auto_accept_confidence`).
- `config/taxonomy.toml` — категории и keyword-правила (правятся и через `/settings`).
- **LLM не обязателен.** Три режима (проверить: `uv run spendtrack llm-status`):
  1. **Выключен (по умолчанию)** — без настройки ни одного сетевого вызова; спорные строки ждут подтверждения.
  2. **Свой LLM (BYO) / Ollama — рекомендуется.** Любой OpenAI-совместимый сервер: `SPENDTRACK_LLM_BASE_URL` +
     `SPENDTRACK_LLM_MODEL` + `SPENDTRACK_LLM_API_KEY`; локальный Ollama — `SPENDTRACK_LLM_PROVIDER=ollama`
     (модель по умолчанию `qwen2.5-coder:3b`, нужен `ollama pull`). Данные уходят только на указанный сервер.
  3. **Free-каналы** — осознанный opt-in: `SPENDTRACK_OPENROUTER_API_KEY` и/или `SPENDTRACK_FREEL_LLM_API_KEY`
     (+ `SPENDTRACK_ALLOW_LOCAL_LLM=1` для локальных шимов). Это чужие серверы — см. [`PRIVACY.md`](PRIVACY.md).
- `SPENDTRACK_DB_PATH` — путь к БД (по умолчанию `data/spend.db`).

![Настройки](assets/screenshot-settings.png)

## Приватность и безопасность

- **Офлайн по умолчанию:** без ключей LLM приложение не делает сетевых вызовов (проверяется тестом
  `tests/test_offline.py` в CI); сервер слушает только `127.0.0.1`, телеметрии нет.
- **Что уходит при включённом LLM** (описание ≤300 симв., сумма, псевдоним счёта, дата и few-shot примеры) —
  подробно в [`PRIVACY.md`](PRIVACY.md); для полного контроля подключите свой ключ (BYO) или локальный Ollama
  (см. «Настройка»). Модель угроз и лимиты — [`SECURITY.md`](SECURITY.md).
- Лимиты импорта: CSV ≤ 10 МБ; абсурдные суммы отбрасываются в отчёт (`invalid`), а низкоуверенные строки
  уходят в очередь «Подтвердить».
- Данные — ваш файл SQLite (`data/spend.db`); бэкап с проверкой восстановления: `uv run python scripts/backup.py`.
- Не финансовый/налоговый совет; ПО поставляется «как есть» (AGPLv3).

## Разработка

```bash
uv run pytest              # unit-тесты (LLM всегда стаб, сеть не нужна)
uv run pytest -m e2e       # Playwright: реальный uvicorn на временном порту и временной БД
uv run ruff check src tests
```

- Суммы хранятся в копейках (`INTEGER`), БД — SQLite в WAL, миграции — по `PRAGMA user_version`.
- Архитектура и решения: [`spec/ARCHITECTURE.md`](spec/ARCHITECTURE.md) · контур верификации: [`spec/PIPELINE.md`](spec/PIPELINE.md) · стек и деплой: [`spec/stack.md`](spec/stack.md) · словарь: [`CONTEXT.md`](CONTEXT.md).
- Изменения: [`CHANGELOG.md`](CHANGELOG.md).

## Бэкап

```bash
uv run python scripts/backup.py --keep 14   # VACUUM INTO, безопасно при WAL
```

## English

Local-first personal expense tracker (FastAPI + SQLite + htmx): import bank CSV (Sber/Tinkoff/Yandex formats),
deterministic rule-based categorization with an optional LLM fallback for the rest (bring your own API key or a
local Ollama model), human review queue, budgets, subscription detection and a weekly anomaly digest — all on
your machine, no cloud, no bank APIs.
Quick start: `uv sync && uv run uvicorn spendtrack.main:app --port 8766`; demo with synthetic data:
`uv run python scripts/demo_data.py seed`. UI is Russian for now (English localization is on the roadmap).

## Лицензия и поддержка

**AGPLv3** — см. [`LICENSE`](LICENSE). Почему: продукт про приватность и локальные данные — сетевой копилефт не даёт
превратить код в закрытый облачный сервис, при этом self-host, форки и вклад остаются свободными (без CLA).

Проект бесплатный. С релизом планируется модель «Supporter»: разовая лицензия (~$25 / 1900 ₽) за готовые сборки,
автообновление и managed-LLM-прокси (ядро не кастрируется). Каналы поддержки появятся здесь же (Boosty).
