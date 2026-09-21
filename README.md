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
«Импорт» на главной → выберите CSV; формат банка определяется автоматически. Отчёт покажет, сколько строк
добавлено, сколько пропущено (и почему) и что показалось подозрительным. У каждой операции есть
невидимый отпечаток, поэтому повторная загрузка того же файла ничего не добавляет.
</details>

<details>
<summary><strong>Банк изменил формат выписки — что делать?</strong></summary>
Импорт честно скажет, каких колонок не хватает, и не тронет базу. Пришлите обезличенный образец (первые строки)
в <a href="https://github.com/ExNihil14/spend-tracker/issues/new">issue</a> — адаптер обновим.
Обезличить: <code>python scripts/anonymize.py выписка.csv</code> — описания, магазины и номера карт заменятся
псевдонимами, а формат выписки (колонки, даты, суммы) сохранится.
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
Поделиться анонимной статистикой (сколько операций и т.п.) можно только вручную — `spendtrack doctor --share`
печатает сводку и ссылку на issue; приложение само ничего не отправляет.
</details>

<details>
<summary><strong>Как сделать бэкап или забрать данные?</strong></summary>
Экспорт CSV/Excel — кнопкой на главной; бэкап базы — `uv run python scripts/backup.py` (консистентный
снимок через `VACUUM INTO`, работает при запущенном приложении); путь к базе — `spendtrack paths`.

<b>Копия вне компьютера</b> (защита от поломки диска): `uv run python scripts/backup.py --copy-to E:\spendtrack-backup`
— скрипт откажется писать копию на тот же диск, что и база, проверит контрольную сумму и оставит отметку.
`spendtrack doctor` проверит и локальный бэкап, и внешнюю копию (файл на месте, не повреждена, свежее 7 дней).
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

<details>
<summary><strong>Codespaces: если что-то не так</strong></summary>

- **Приложение не открылось:** вкладка **PORTS** → порт `8766` → «Open in Browser». Сервер стартует автоматически
  при подключении к codespace; лог — `tail -f /tmp/spendtrack.log`, ручной запуск — `bash .devcontainer/start-app.sh`.
- **После обновления кода страница отдаёт 500:** работает старый процесс (шаблоны Jinja горячие, Python — нет):
  `pkill -f "uvicorn spendtrack" && bash .devcontainer/start-app.sh` или Stop/Start codespace.
- **Страница порта отдаёт GitHub 404:** проверьте, что codespace запущен и вы вошли в GitHub (порт приватный);
  после Rebuild Container порт мог «переехать» — Stop → Start и откройте порт заново; обходной путь — Simple Browser
  внутри VS Code вместо прямого URL.
</details>


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

## Работа в фоне (автозапуск)

Приложение можно запускать автоматически — при входе в систему или загрузке компьютера. Сервер в любом случае
слушает только `127.0.0.1`; где лежат база и настройки — покажет `spendtrack paths`. Путь к `spendtrack.exe`
в примерах ниже — стандартный для установки одной командой (`uv tool`); если ставили иначе, подставьте свой.

### Windows — Планировщик заданий

Проще всего и не требует прав администратора; запуск при входе в систему (PowerShell):

```powershell
$exe = "$env:USERPROFILE\.local\bin\spendtrack.exe"
Register-ScheduledTask -TaskName spendtrack -Force `
  -Action  (New-ScheduledTaskAction -Execute $exe -Argument "serve") `
  -Trigger (New-ScheduledTaskTrigger -AtLogOn)
Start-ScheduledTask spendtrack
```

Остановить/убрать: `Stop-ScheduledTask spendtrack` / `Unregister-ScheduledTask spendtrack -Confirm:$false`.
Проверка: <http://127.0.0.1:8766/health>.

### Windows — NSSM (служба, работает до входа в систему)

Нужны права администратора. Один раз поставьте [NSSM](https://nssm.cc/) (`winget install nssm`), затем:

```powershell
nssm install spendtrack "$env:USERPROFILE\.local\bin\spendtrack.exe" serve
nssm set spendtrack AppEnvironmentExtra "SPENDTRACK_CONFIG_DIR=$env:APPDATA\spendtrack" "SPENDTRACK_DATA_DIR=$env:LOCALAPPDATA\spendtrack"
nssm set spendtrack Start SERVICE_AUTO_START
nssm start spendtrack
```

Служба работает от системной учётной записи, поэтому папки данных и настроек передаются ей явно (те же, что
показывает `spendtrack paths`). Управление: `nssm restart spendtrack`, `nssm stop spendtrack`,
`nssm remove spendtrack confirm`.

### macOS — launchd

```bash
curl -LsSf https://raw.githubusercontent.com/ExNihil14/spend-tracker/main/deploy/com.spendtrack.serve.plist \
  -o ~/Library/LaunchAgents/com.spendtrack.serve.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.spendtrack.serve.plist
```

Перезапуск — `launchctl kickstart -k gui/$(id -u)/com.spendtrack.serve`, убрать —
`launchctl bootout gui/$(id -u)/com.spendtrack.serve`. Логи: `/tmp/spendtrack.out.log` (временные; свой путь
задаётся в plist — `StandardOutPath`).

### Linux — systemd (пользовательская служба, без root)

```bash
mkdir -p ~/.config/systemd/user
curl -LsSf https://raw.githubusercontent.com/ExNihil14/spend-tracker/main/deploy/spendtrack.service \
  -o ~/.config/systemd/user/spendtrack.service
systemctl --user daemon-reload
systemctl --user enable --now spendtrack
loginctl enable-linger $USER    # запускать, даже когда вы не в системе (по желанию)
```

Статус и логи: `systemctl --user status spendtrack`, `journalctl --user -u spendtrack -f`.

**Ключи LLM для сервиса** (если включили BYO): переменные `SPENDTRACK_LLM_*` должны быть видны процессу —
допишите их в юнит (`systemctl --user edit spendtrack`), в `EnvironmentVariables` plist или в
`nssm set spendtrack AppEnvironmentExtra …`. Сами ключи в `deploy/` не хранятся.

## Команды

| Команда | Что делает |
|---|---|
| `spendtrack serve [--port N] [--open]` | запускает интерфейс |
| `spendtrack import file.csv --bank auto [--json]` | импорт выписки (отчёт «добавлено/пропущено/подозрительно») |
| `spendtrack add -23.45 "milk"` | добавить расход вручную |
| `spendtrack report --month 2026-09` | отчёт за месяц |
| `spendtrack budget` | прогресс по бюджетам |
| `spendtrack recurring` | найденные подписки |
| `spendtrack digest` | дайджест недели и аномалии |
| `spendtrack export --format csv` | выгрузка CSV/XLSX |
| `spendtrack doctor [--share]` | проверка целостности данных (+ анонимная сводка вручную) |
| `python scripts/backup.py --copy-to E:\backup` | бэкап базы + копия на другой диск |
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
`uv run python scripts/demo_data.py seed`. Runs as a background service too (Windows Task Scheduler/NSSM,
macOS launchd, Linux systemd — templates in `deploy/`; see the «Работа в фоне» section). UI is Russian for now
(English localization is on the roadmap).

## Лицензия и поддержка

**AGPLv3** — см. [LICENSE](LICENSE). Почему: продукт про приватность и локальные данные — сетевой копилефт
не даёт превратить код в закрытый облачный сервис, при этом self-host, форки и вклад остаются свободными.

Проект бесплатный. Модель «Supporter» — разовая лицензия (~$25 / 1900 ₽) за готовые сборки, автообновление
и managed-LLM-прокси (ядро не кастрируется). Поддержать: [Boosty](https://boosty.to/REPLACE_ME)
(ссылка появится к запуску) · интерес к лицензии — [issue Supporter](https://github.com/ExNihil14/spend-tracker/issues/new?template=supporter.yml).

Не финансовый и не налоговый совет; ПО поставляется «как есть».
