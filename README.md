# Spendtrack

[![CI](https://github.com/ExNihil14/spend-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/ExNihil14/spend-tracker/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ExNihil14/spend-tracker)

**Трекер личных расходов, который живёт на вашем компьютере.** Закиньте выписку из банка — получите
категории, бюджеты, список подписок и короткий отчёт о необычных тратах. Без облака, без подписки,
без передачи данных третьим лицам.

![Список транзакций](assets/screenshot-transactions.png)

Сайт с демо: **<https://exnihil14.github.io/spend-tracker/>**

## Что умеет

- **Импорт выписок** Сбера, Тинькофф и Яндекса: формат определяется автоматически, повторный импорт того же файла
  не создаёт дубликатов.
- **Категории почти без ручной работы:** сначала срабатывают ваши правила и «память» о магазинах, затем — ИИ
  (если подключите), а спорные операции попадают в очередь «Подтвердить». Одобренная правка запоминается.
- **Бюджеты по категориям** — месячные лимиты и прогресс: видно, где ещё есть запас, а где перерасход.
- **Подписки** — приложение само находит регулярные списания и предупреждает, если цена выросла.
- **Дайджест недели** — расходы и доходы, топ-категории, самые дорогие дни и аномалии (крупные суммы,
  возможные дубликаты, скачки цен).
- **Экспорт без потерь** — все операции выгружаются в CSV или Excel одной кнопкой; данные всегда можно забрать с собой.
- **Проверка данных** — встроенный `doctor` проверяет целостность базы и состояние бэкапов.

## Кому подойдёт

- Тем, кто **не хочет отдавать банковские данные в облако** и готов раз в месяц загрузить CSV-выписку.
- Тем, кому нужны бюджеты, подписки и отчёт об аномалиях **без подписки и bank-API**.
- Пользователям Windows, macOS и Linux — приложение работает локально, интернет не обязателен.

**Не подойдёт:** тем, кто ждёт автоматическую синхронизацию с банком или мобильное приложение из магазина;
семьям с общим бюджетом (приложение на одного пользователя); учёту инвестиций и мультивалютным портфелям.

## Установка

### Одна команда

Windows (PowerShell):

```powershell
powershell -c "irm https://raw.githubusercontent.com/ExNihil14/spend-tracker/main/install.ps1 | iex"
```

macOS / Linux / WSL:

```bash
curl -LsSf https://raw.githubusercontent.com/ExNihil14/spend-tracker/main/install.sh | sh
```

Скрипт сам поставит всё необходимое (менеджер `uv` и Python) и запустит интерфейс. Дальше приложение
открывается командой `spendtrack serve --open`, а `spendtrack paths` покажет, где лежат база и настройки.

### Docker (если так удобнее)

```bash
docker build -t spendtrack .
docker run --rm -p 127.0.0.1:8766:8766 -v spendtrack-data:/data spendtrack
```

Данные — в томе `spendtrack-data`; наружу публикуется только localhost.

### Из исходников (для разработки)

```bash
git clone https://github.com/ExNihil14/spend-tracker.git
cd spend-tracker
uv sync
uv run spendtrack serve      # или .\run.ps1 на Windows
```

Приложение откроется на <http://127.0.0.1:8766>; база создастся сама.

## Первые шаги

1. **Импортируйте выписку** — кнопка «Импорт» на главной, выберите CSV из банка.
2. **Пройдите «Подтвердить»** — подтвердите или исправьте категории, в которых ИИ не был уверен.
3. **Задайте бюджеты** — «Настройки» → «Бюджеты», по категориям.
4. **Смотрите «Дашборд»** — бюджеты, подписки, дайджест недели и графики.

Подробная справка со словарём терминов и легендой значков — на странице **«Помощь»** внутри приложения
(меню → Помощь).

## Частые вопросы

<details>
<summary><strong>Нужен ли API-ключ или интернет?</strong></summary>
Нет. По умолчанию ИИ выключен, и приложение работает полностью офлайн — на правилах и ваших правках.
</details>

<details>
<summary><strong>Как импортировать выписку и что с дубликатами?</strong></summary>
«Импорт» на главной → выберите CSV; формат банка определяется автоматически. У каждой операции есть
невидимый отпечаток, поэтому повторная загрузка того же файла ничего не добавляет.
</details>

<details>
<summary><strong>Почему операции попадают в «Подтвердить»?</strong></summary>
Это строки, в категории которых ИИ не был уверен (уверенность ниже порога). Вы подтверждаете или меняете
категорию — приложение запоминает выбор для этого магазина.
</details>

<details>
<summary><strong>Куда уходят мои данные?</strong></summary>
Никуда, пока вы сами не подключите ИИ. Сервер слушает только `127.0.0.1`, телеметрии нет. Что именно уходит
при включённом ИИ — в [PRIVACY.md](PRIVACY.md); модель угроз — в [SECURITY.md](SECURITY.md).
</details>

<details>
<summary><strong>Как сделать бэкап или забрать данные?</strong></summary>
Экспорт CSV/Excel — кнопкой на главной; бэкап базы — `uv run python scripts/backup.py`; путь к базе —
`spendtrack paths`. `spendtrack doctor` подскажет, всё ли в порядке.
</details>

## Демо без своих данных

Синтетическая витрина (~5 месяцев): подписки со скачком цены, аномалии, бюджеты с перерасходом, очередь
подтверждения. Реальная база не затрагивается.

```bash
uv run python scripts/demo_data.py seed     # данные в data/demo.db
uv run python scripts/demo_data.py status   # что засеяно
uv run python scripts/demo_data.py clean    # убрать демо
```

**Посмотреть в браузере без установки:** [создать Codespace](https://codespaces.new/ExNihil14/spend-tracker) —
контейнер сам всё поставит, запустит приложение и засеет демо-данные (квота GitHub Free: 120 core-часов/мес).
Порт приватный: приложение увидите только вы.

## Настройка

- `config/settings.toml` — порт, порог авто-приёма категорий, адреса LLM-серверов.
- `config/taxonomy.toml` — категории и правила (удобнее править через «Настройки» в интерфейсе).
- `SPENDTRACK_DB_PATH` — путь к базе (по умолчанию `data/spend.db`).

**ИИ — необязателен.** Три режима (проверить: `spendtrack llm-status`):

1. **Выключен (по умолчанию).** Никаких сетевых вызовов; спорные операции ждут подтверждения.
2. **Свой сервер или локальная модель (рекомендуется).** Любой OpenAI-совместимый сервер:
   `SPENDTRACK_LLM_BASE_URL` + `SPENDTRACK_LLM_MODEL` + `SPENDTRACK_LLM_API_KEY`; локальный Ollama —
   `SPENDTRACK_LLM_PROVIDER=ollama`. Данные уходят только на указанный вами сервер.
3. **Бесплатные каналы** — осознанный выбор: ключи OpenRouter/FreeLLM (`SPENDTRACK_OPENROUTER_API_KEY`
   и/или `SPENDTRACK_FREEL_LLM_API_KEY`). Это чужие серверы — см. [PRIVACY.md](PRIVACY.md).

![Настройки](assets/screenshot-settings.png)

## Команды

| Команда | Что делает |
|---|---|
| `spendtrack serve [--port N] [--open]` | запускает интерфейс |
| `spendtrack import file.csv --bank auto` | импорт выписки |
| `spendtrack add -23.45 "milk"` | добавить расход вручную |
| `spendtrack report --month 2026-09` | отчёт за месяц |
| `spendtrack budget` | прогресс по бюджетам |
| `spendtrack recurring` | найденные подписки |
| `spendtrack digest` | дайджест недели и аномалии |
| `spendtrack export --format csv` | выгрузка CSV/XLSX |
| `spendtrack doctor` | проверка целостности данных |
| `spendtrack paths` | где лежат база и настройки |
| `spendtrack llm-status` | какой режим ИИ сейчас |
| `spendtrack confidence` | калибровка порога авто-приёма |

![Дашборд](assets/screenshot-dashboard.png)

## Разработка

```bash
uv run pytest              # unit-тесты (сеть не нужна, LLM подменяется)
uv run pytest -m e2e       # браузерные тесты (Playwright)
uv run ruff check src tests
```

- Архитектура и решения: [spec/ARCHITECTURE.md](spec/ARCHITECTURE.md) · контур верификации:
  [spec/PIPELINE.md](spec/PIPELINE.md) · стек: [spec/stack.md](spec/stack.md) · словарь: [CONTEXT.md](CONTEXT.md).
- Изменения: [CHANGELOG.md](CHANGELOG.md).

## English

Local-first personal expense tracker (FastAPI + SQLite + htmx): import bank CSV (Sber/Tinkoff/Yandex formats),
deterministic rule-based categorization with an optional LLM fallback for the rest (bring your own API key or a
local Ollama model), review queue, budgets, subscription detection and a weekly anomaly digest — all on your
machine, no cloud, no bank APIs. Quick start: `uv sync && uv run spendtrack serve`; demo with synthetic data:
`uv run python scripts/demo_data.py seed`. UI is Russian for now (English localization is on the roadmap).

## Лицензия и поддержка

**AGPLv3** — см. [LICENSE](LICENSE). Почему: продукт про приватность и локальные данные — сетевой копилефт
не даёт превратить код в закрытый облачный сервис, при этом self-host, форки и вклад остаются свободными.

Проект бесплатный. Модель «Supporter» — разовая лицензия (~$25 / 1900 ₽) за готовые сборки, автообновление
и managed-LLM-прокси (ядро не кастрируется). Поддержать: [Boosty](https://boosty.to/REPLACE_ME)
(ссылка появится к запуску) · интерес к лицензии — [issue Supporter](https://github.com/ExNihil14/spend-tracker/issues/new?template=supporter.yml).

Не финансовый и не налоговый совет; ПО поставляется «как есть».
