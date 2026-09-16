# CONTEXT.md — словарь домена Spendtrack

Короткий словарь для агентов. Используй эти термины вместо перифразов.

## Термины
- **Транзакция** — одна операция (доход/расход) из банка или CLI. Поля: date, description, amount_kopecks (INTEGER копеек), category, category_source, confidence, merchant, account_anon, import_batch, fingerprint, category_llm, review_status.
- **Сумма** — всегда `amount_kopecks` INTEGER (копейки). −12345 = −123.45₽. НИКОГДА не REAL. `parse_amount(str) → int`, `fmt_amount(int) → "−123.45"`.
- **Категория** — одна из 18 в `config/taxonomy.toml` (groceries, restaurants, transport, fuel, housing, utilities, internet-phone, subscriptions, health, education, entertainment, clothing, household, transfers, income, taxes, travel, other).
- **Источник категории** (`category_source`) — как получена: `rule` (keyword-правило), `llm` (принято от LLM, conf≥0.9), `llm_pending_review` (низкая уверенность → в очередь), `import` (из CSV банка), `manual` (создано вручную), `correction` (правка юзера).
- **Подтверждение (review queue)** — транзакции с `review_status='pending'` (ставится при `category_source='llm_pending_review'` — LLM дал conf<0.9 или категорию вне таксономии). `category_llm` — предложение LLM (не перезаписывается → рендер-diff). `approve` → `category`=выбранная + `category_source='rule'`; `skip` → вне очереди, категория не меняется; `approve-all` → `category=COALESCE(category_llm, category, 'other')`.
- **Мерчант** — нормализованное имя (UPPER). `merchant_cache` → связанная категория (выигрывает над правилами/LLM).
- **Fingerprint** = sha1(date|kopecks|norm(desc)|account_anon|export_rowid). Дедуп импорта: повторный импорт = no-op. norm = UPPER + collapse пробелов.
- **Партия импорта (import_batch)** — один загруженный CSV, id `b_hex`, sha256 содержимого, статус.
- **Псевдоним счёта (account_anon)** — `acc_hex8`; сырой номер карты НЕ хранится (`account_pseudonyms`).
- **Примеры (examples)** — few-shot для LLM (правки юзера навсегда).
- **Бюджет** — месячный лимит категории в `budgets(category, amount_kopecks)` (SQLite, не TOML). Одна константа на все месяцы, без rollover. Считаются расходы месяца (знаковая сумма: возвраты уменьшают). Доход/переводы (`BUDGET_EXCLUDED`) не бюджетируются. Пусто/0 = снят. Редактор — `/settings`, прогресс — `/dashboard`, CLI `spendtrack budget`.
- **Doctor** — проверка целостности данных: CLI `spendtrack doctor [--json]`, API `GET /health/data`. Severities: `critical` (битая БД/схема, категории транзакций вне таксономии), `warn` (данные вне очереди/таксономии, бэкап >48ч), `info` (пустые партии, нет папки бэкапов), `ok`. Exit 1 — только при critical; API 503 — при critical. Авторемонта нет.
- **Рекурринг/подписка** — повторяющееся списание: ≥3 расхода мерчанта с суммами в ±5% медианы кластера и интервалами 27–34 дн (медиана 28–31; допускается 1 пропуск месяца: разрыв 56–62 дн). «Цена» = медиана кластера, `active` = последнее списание ≤40 дн назад. Считается на лету, не хранится: CLI `spendtrack recurring [--json]`, карточка на `/dashboard` (`recurring_summary`, JSON-ключ `subscriptions` — не `items`, т.к. в Jinja `dict.items` — метод).

## Правила
- Ядро детерминированное и оффлайн; LLM — единственный шов, всегда инжектируемый в тестах.
- Правило «Суммы = копейки» и «не менять fingerprint-контракт без тестов» — не нарушать.
- Тесты: только швы `classify_with_injectable`, `import_csv(classify=)`, `parse_amount`, `fingerprint`; оффлайн через стаб.