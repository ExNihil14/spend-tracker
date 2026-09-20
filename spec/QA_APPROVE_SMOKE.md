# QA: визуальный smoke очереди подтверждения `/approve`

Роль: Senior QA. Цель — дать человеку однозначные кейсы и критерии, чтобы глазами
оценить работу очереди подтверждения категоризации LLM (Work 3) на живом сервере.

## 1. Окружение и доступ

| Параметр | Значение |
|---|---|
| URL | http://localhost:8766 |
| Сервис | NSSM `spendtrack` (`python -m uvicorn spendtrack.main:app --port 8766`) |
| Перезапуск | `nssm restart spendtrack` (PowerShell) |
| БД | `D:\dev\personal\spend-tracker\data\spend.db` (SQLite, WAL) |
| Активная таксономия | 18 категорий, keyword-правила в `config/taxonomy.toml` |
| Порог авто-приёма | `auto_accept_confidence = 0.9` |

Порядок подготовки:
```powershell
nssm restart spendtrack
# засеять детерминированные pending-записи (8 шт):
uv run python scripts/review_demo.py seed     # workdir = корень проекта
# после проверки — убрать демо-строки:
uv run python scripts/review_demo.py clean
```
Демо-строки помечены `import_batch='DEMO_REVIEW'`, мерчанты — префиксом «ДЕМО »,
поэтому очистка не затрагивает реальные данные.

## 2. Бизнес-логика (что и почему попадает в очередь)

Пайплайн категоризации (`categorize.py`), приоритет сверху вниз:
1. **merchant_cache** — если мерчант уже подтверждался человеком → берём оттуда.
2. **keyword-правило** (`taxonomy.toml`) → `category_source='rule'`, `confidence=1.0`, `review_status='approved'` — **в очередь НЕ попадает**.
3. **LLM** (`llm.py`, маршрут BYO/Ollama → free-цепочка (OpenRouter :free → FreeLLMAPI → abacus-web/DeepSeek) → offline — канон в `spec/ARCHITECTURE.md`):
   - `confidence >= 0.9` → `source='llm'`, `approved`, мерчант кладётся в кэш — **в очередь НЕ попадает**;
   - `confidence < 0.9` → `source='llm_pending_review'`, **`review_status='pending'` — в очередь**;
   - LLM вернул категорию вне таксономии → `category='other'`, `confidence=0.0`, `category_llm=<сырое>`, `pending` — в очередь.

### Модель полей (транзакция)
- `category` — категория в БД (итоговая).
- `category_llm` — **предложение LLM**. Не перезаписывается → на экране виден diff “LLM предложил X (в БД: Y)”.
- `review_status` — состояние очереди: `pending` → `approved` | `skipped`.
- `category_source` — `rule` | `llm` | `llm_pending_review` | `correction`.

### Диаграмма состояний
```
[LLM conf<0.9] --(create/import)--> pending
pending --approve(категория)--> approved   (category := выбранная, source := 'rule', merchant_cache := запись)
pending --skip-->              skipped     (категория НЕ меняется)
pending --approve-all-->       approved    (category := COALESCE(category_llm, category, 'other'), source := 'rule',
                                            merchant_cache := запись для строк с мерчантом; 16.09)
approved/skipped --approve/skip--> 409 «запись не в очереди» (терминальные)
```

### Правила очереди
- Сортировка: `date ASC, ABS(amount) DESC, id ASC` («крупные сверху», знак не важен).
- Счётчик `pending_count` = `COUNT(*) WHERE review_status='pending'`.
- Рендер очереди — единый фрагмент `partials/review_rows.html` (страница и htmx-ответы идентичны).
- Все действия (`approve`/`skip`/`approve-all`) возвращают перерисованный фрагмент + OOB-обновление бейджа `#pending-count`, целевой swap — `#review-rows` (`outerHTML`).

## 3. Тест-кейсы

Приоритет: P1 — блокирующие для доверия к данным, P2 — важные, P3 — косметика.

### TC-01 (P1) Пустое состояние
- Шаги: `clean`, открыть `/approve`.
- Ожидаемо: таблица пуста, строка «Все подтверждены»; в навигации бейдж «Подтвердить 0».
- Критерий: нет ни одной строки-транзакции; текст-заглушка присутствует.

### TC-02 (P1) Очередь показывает pending и сортировку
- Шаги: `seed`, открыть `/approve`.
- Ожидаемо: ровно 8 строк. Порядок по дате возрастанию (05→11 сентября).
  На 11 сентября «ДЕМО ПОКУПКА (5 000 ₽)» (−5000) стоит **выше** «ДЕМО ПОКУПКА (1 000 ₽)» (−1000),
  т.к. сортировка — `ABS(amount) DESC` («крупные по модулю выше»).
- Критерий: порядок строк соответствует `date ASC, ABS(amount) DESC, id ASC`.

### TC-03 (P1) Diff «предложение LLM vs категория в БД»
- Строка «СТРОЙКАОПТ МСК…»: категория-бейдж = `household`, рядом серая сноска «(в БД: other)».
- Строка «ПЕРЕВОД ДРУГУ ИВАН»: `category_llm == category == transfers` → сноски НЕТ.
- Критерий: сноска появляется только когда `category_llm != category`; цвет бейджа = цвет `category_llm`.

### TC-04 (P1) Отображение суммы
- Отрицательные суммы — красным (`text-rose-400`), положительная «ВОЗВРАТ OZON» (+1290 ₽) — зелёным (`text-emerald-400`).
- Критерий: знак и цвет совпадают; формат `X.XX` (2 знака).

### TC-05 (P1) Пропуск (skip)
- Шаги: у строки нажать «Пропустить».
- Ожидаемо: строка исчезает, остальные не двигаются; бейдж в навигации уменьшается на 1; тост/индикатор не зависает.
- Критерий: `review_status='skipped'` (проверка: `scripts/review_demo.py list` не показывает строку); повторный skip той же записи невозможен (её уже нет в очереди).

### TC-06 (P1) Одобрение с предложенной категорией
- Шаги: у строки **не менять** select (по умолчанию = `category_llm`) и нажать «Одобрить».
- Ожидаемо: строка исчезает, бейдж −1.
- Критерий: на главной `/` у этой транзакции `category` = предложенная LLM, источник = `rule`, `review_status='approved'`.

### TC-07 (P1) Одобрение со сменой категории (правка человека)
- Шаги: у строки «АЗС №17 ТРАССА» выбрать в select `transport` (менять с `fuel`) и нажать «Одобрить».
- Ожидаемо: строка исчезает; транзакция получает `category=transport`, `source='rule'`.
- Критерий: смена одного клика работает (htmx без перезагрузки), данные сохранены.

### TC-08 (P1) «Одобрить все»
- Шаги: нажать «Одобрить все» → подтвердить диалог (`hx-confirm` показывает число записей).
- Ожидаемо: все строки исчезают, появляется «Все подтверждены», бейдж = 0.
- Критерий: ни одной pending не осталось (проверка `list`); каждая получила `category=category_llm` (или `category`, если предложения не было).

### TC-09 (P1) Синхронность счётчика (OOB)
- Шаги: выполнить любое действие (TC-05/06/08).
- Ожидаемо: бейдж `#pending-count` в навигации обновляется без перезагрузки страницы.
- Критерий: значение бейджа = реальному `pending_count`.

### TC-10 (P2) Автообновление главной
- Шаги: после одобрения перейти на `/`.
- Ожидаемо: транзакция отображается с новой категорией и источником `rule`; в очереди её нет.
- Критерий: данные консистентны между `/` и `/approve`.

### TC-11 (P2) Few-shot: правка влияет на будущую категоризацию
- Шаги: одобрить строку «ДЕМО КОФЕЙНЯ …» с категорией `restaurants`; затем на `/` добавить новую трату с тем же описанием/мерчантом.
- Ожидаемо: новая трата получает `restaurants` **из кэша мерчанта**, `source='rule'`, в очередь НЕ попадает.
- Критерий: `merchant_cache` содержит запись; повторная классификация не идёт в LLM.
- Важно: с 16.09 кэш засевается и для одиночного approve, и для **approve-all** (few-shot-цикл единый; см. §5).

### TC-12 (P3) Негатив: неизвестный id
- Шаги: `curl -X POST http://localhost:8766/api/reviews/999999/approve -d "category=food"`.
- Ожидаемо: HTTP 404 «не найдено».

### TC-13 (P3) Негатив: категория вне таксономии
- Шаги: `curl -X POST .../api/reviews/<pending_id>/approve -d "category=hacker_cat"`.
- Ожидаемо: HTTP 422 «категория … вне таксономии»; запись остаётся pending.

### TC-14 (P3) Негатив: approve/skip не-pending
- Шаги: повторить approve/skip для уже обработанной записи.
- Ожидаемо: HTTP 409 «запись не в очереди».

### TC-15 (P3) Дашборд
- Шаги: `seed`, открыть `/dashboard`.
- Ожидаемо: бейдж «Подтвердить N» показывает N>0 (фикс этого прогона).
- Критерий: счётчик на `/dashboard` совпадает с `/approve`.

## 4. Критерии приёмки (Definition of Done smoke)

1. Все P1-кейсы пройдены на живом сервере 8766 в браузере.
2. Ни одного «зависшего» индикатора `#global-indicator` (оверлей не перехватывает клики).
3. Счётчик бейджа консистентен на `/`, `/dashboard`, `/approve` в любой момент.
4. После действий данные видны на `/` и `/dashboard` (нет рассинхрона UI и БД).
5. `clean` возвращает систему в исходное пустое состояние.

## 5. Найденные замечания

| # | Severity | Описание | Статус |
|---|---|---|---|
| 1 | Minor | `/dashboard` рендерил бейдж `#pending-count` = 0 (в контекст не передавался `pending`); `base.html` использует `pending|default([])|length`. | **Исправлено** в этом прогоне (+ тест `test_dashboard_badge_shows_pending`) |
| 2 | Info/Design | `approve-all` **не** вызывает `seed_merchant_cache` (в отличие от одиночного `approve`), поэтому массовое принятие LLM-догадок НЕ пополняет few-shot кэш. | **Исправлено 16.09:** пачка засевает кэш для строк с мерчантом (единый few-shot-цикл; + тест `test_approve_all_seeds_merchant_cache`) |
| 3 | Minor | Очередь в UI ограничена `LIMIT 500` (`list_transactions` default), при этом `approve-all` обрабатывает все pending. При >500 записей отобразятся не все. | Известное ограничение |
| 4 | Minor | Кнопка «Одобрить все» активна и при 0 записей (диалог «…0 записей?» → no-op). | **Исправлено** рефактором фрагментов (`511b630`): кнопка живёт/исчезает вместе с очередью; тесты `test_approve_all_button_hidden_when_empty/_present_when_pending` |
| 5 | Info | Эндпоинты `GET /api/reviews` и `GET /api/reviews/count` не используются шаблонами (кандидаты на удаление либо на подключение live-обновления). | **Оставлено осознанно** (16.09): JSON/HTML-контракт для smoke/скриптов; покрыто тестами `test_reviews_page_lists_pending`, `test_reviews_get_fragment`; zero-cost для соло |
| 6 | Info/Design | Внутри одной даты сортировка `amount DESC` — **числовая**: у расходов меньший по модулю оказывается выше (например, −1000 над −5000). Если целью было «крупные расходы выше», нужно `ORDER BY abs(amount) DESC`. | **Исправлено 16.09 (решение юзера):** внутри дня `ABS(amount) DESC` — «крупные сверху»; канон `spec/ARCHITECTURE.md` и тест обновлены |
| 7 | Fixed | **Одобрить «как предложено» было невозможно**: approve висел только на `change` у select (выбор того же значения событие не вызывает). Добавлена кнопка «Одобрить» рядом с select (select остался для смены категории); e2e `approve_as_proposed` + `approve_with_category`. | **Исправлено** |
| 8 | Fixed | Кнопки без `cursor:pointer` — Tailwind v4 preflight ставит `cursor:default`. Глобальный стиль `button:not(:disabled){cursor:pointer}` в `base.html`. | **Исправлено** |
| 9 | Fixed | «Одобрить все» оставалась при пустой очереди (модалка «одобрить 0»). Кнопка стала OOB-фрагментом (`partials/approve_all.html`), исчезает вместе с очередью; +2 API-теста. | **Исправлено** |
| 10 | Fixed | Графики `/dashboard` периодически не рисовались при переходе через `hx-boost` (гонка загрузки Chart.js). Библиотека перенесена в `head`, инициализация через `htmx.onLoad` + guard `dataset.init`; +e2e `dashboard_charts_render_via_boost`. | **Исправлено** |
| 11 | Fixed | Долгий спиннер при добавлении расхода: мёртвый primary (FreeLLMAPI/WSL) давал +3с коннект-таймаут до живого OpenRouter. `settings.toml`: primary → OpenRouter :free, FreeLLMAPI — резерв (вернуть после оживления WSL/Abacus 20.09). | **Исправлено** |
| 12 | Improved | **UX approve/skip (анализ субагента):** спиннер отклонён — операция 5–30 мс (< Doherty) даёт flicker; нужна преемственность. Внедрено: fade-уход строки 160 мс (`hx-target="closest tr"`, `hx-swap="outerHTML swap:160ms"`), `hx-disabled-elt="find button"` (двойной клик), OOB-плейсхолдер «Все подтверждены» (`beforeend`/`delete`), a11y `prefers-reduced-motion`. Ответ approve/skip = только OOB-части. | **Исправлено** |
| 13 | Improved | **Toast-подтверждение** (2-й приоритет UX-анализа): OOB-тост «Одобрено: <категория> — <описание>» / «Пропущено: …» / «Одобрено записей: N», `role="status"` + `aria-live`, авто-скрытие 1.8 с (скрипт на `htmx:oobAfterSwap` в base.html). | **Внедрено** |

## 6. Быстрые команды проверки БД (не через UI)
```powershell
uv run python scripts/review_demo.py list          # очередь
uv run python scripts/review_demo.py seed
uv run python scripts/review_demo.py clean
```
