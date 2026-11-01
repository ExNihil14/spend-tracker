# Research: Тимур Шемсединов — канал и подход к AI/архитектуре

Дата: 2026-11-01. Статус: **research only; код/live не трогал.**
Допущение: «по Нашему подходу» = сопоставить его инженерные тезисы с нашим
spec-first/phase-gated/vibecoding-подходом (`MASTER_PLAN.md`, `AGENTS.md`, `spec/`), а не
копировать его стек. Если имелось в виду другое — уточнить; выводы ниже помечены.

## Источники

- [П] `tshemsedinov/feed` README — авторский архив тезисов 2026:
  <https://github.com/tshemsedinov/feed>
- [П] `tshemsedinov/Programming-Knowledge` — «Essential Knowledge for Programmers in 2026»:
  <https://github.com/tshemsedinov/Programming-Knowledge>
- [П] Metarhia Docs: <https://github.com/metarhia/Docs>
- [Ч] YouTube-канал и видео (страницы отдают JS-оболочку, транскрипт не получен):
  <https://www.youtube.com/@TimurShemsedinov>,
  `#AI + Architectural DSL — A New Development Approach` (`75O83pLvGnc`),
  `Architectural Description Language for AI` (`0GZ-Nf8yHEw`),
  `How to build architecture that AI follows...` (`bedsdFbhqhw`),
  `How to Constrain #AI to Maintain Architecture` (`nA-z8DXI5_E`).
- [П] `HowProgrammingWorks/Index` — курсы/исходники: <https://github.com/HowProgrammingWorks/Index>
- [Ч] **Ноутбук, прошлые ресёрчи** (AI-сводки видео/стримов, не первичные транскрипты):
  `D:\dev\docs\vibecoding\out\0GZ-Nf8yHEw.md` (Architectural DSL),
  `qNAjrZ07un0.md` (структуры/три контура), `T90zE4cFjNA.md` (reslop/ревью),
  `KSnSy_pNzvQ.md` (Metarhia/Global Storage), `17RqGlJjb50.md` (AI-горизонт),
  `shem_update_synth.md` (сводка/противоречия).
- [Ч] **Телефон, 01.11.2026**: `C:\Users\HP\.oc-telegram\files\2970-timur-shemsedinov-2026-11-01.md`
  — Telegram-скан `@HowProgrammingWorks` (посты 2190–2209), reslop 12 агентов ACP,
  NextTick/Metarhia pricing; выводы по публичным страницам.

## Ключевые тезисы (с уверенностью)

### 1. «Трёхконтурная разработка» — AI внутри ограничений [П]

Пост 2026-07-19: не генерировать миллионы строк в одном репозитории, а разделить на контуры:

1. **Технологический стек** — runtime, протоколы, хранение, безопасность, наблюдаемость,
   контракты, инфраструктура. Пишется редко/дорого, тщательно тестируется, переиспользуется.
2. **Параметризованные модули** — крупные возможности (auth, платежи, отчёты, workflow),
   метапрограммирование/схемы/декларативные контракты; модуль = семейство сценариев.
3. **Продукт** — доменная модель, схемы, бизнес-правила, конфигурация, немного уникальных
   обработчиков; сотни/тысячи строк.

Тезис: каждый следующий контур **сужает пространство решений**; AI эффективен внутри
**заранее подготовленной системы ограничений**; сильные контуры 1–2 уменьшают контекст AI,
ревью, тесты, миграции.

### 2. AI + Architectural DSL [Ч]

Названия видео 2026: «AI + Architectural DSL — A New Development Approach», «Architectural
Description Language for AI», «How to Constrain #AI to Maintain Architecture». Смысл по
названиям/описаниям: архитектуру нужно описывать **строгим DSL/контрактом**, чтобы AI не
«рисовал» произвольную структуру, а следовал ей; senior-разработчик становится архитектором
ограничений. Транскрипты не проверены — не выдаю детали DSL за факт.

### 3. «Empty loop» / Ralph Loop [П]

Пост 2026-03-15: AI-цикл без **новых вводных** на каждой итерации усиливает собственные ошибки
и шум. Первый проход — максимально полный; следующий — только с обратной связью/ограничением/
контекстом; иначе итерация бессмысленна. Это прямо совпадает с нашим правилом «не гонять
итерации вхолостую» (`AGENTS.md`, MASTER_PLAN).

### 4. Документация как вход AI [П]

Посты 2026-04-21 и 2026-06-18: AI читает markdown/ADR/RFC/design docs; документация становится
важнее; паттерны/контракты/изоляция нужны, чтобы точно объяснять задачу человеку и модели;
код должен оставаться понятным человеку.

### 5. Сложность и LoC [П]

Посты 2026-04-27/2026-06-06: заставлять AI **уменьшать** сложность и объём; каждая строка —
будущая тяжесть; бороться с accidental complexity/оверинженерингом; разделять системный и
прикладной код; DSL/декомпозиция/изоляция/стандартизация/локализация изменений. Пост
2026-05-25: «соревноваться не кто больше генерирует, а кто меньше с тем же результатом».

### 6. Зависимости и supply-chain [П]

Пост 2026-05-18: проверять нужность зависимостей; lockfile; минимальные CI permissions;
secret scanning/push protection; protected main/no force push; AI-generated код проходит
review/tests/scans; AI tools не получают prod secrets/write access. Это близко к нашим
правилам секретов/CI/запрету pandas.

### 7. Metarhia как пример «первого контура» [П]

Metarhia Docs: слои api → domain logic → data access → system code; схемы API/данных/домена;
runtime validation; изоляция/threads; минимальные зависимости; без сторонних библиотек;
тестирование. Это пример сильного контура 1–2, но **Node.js/Postgres/threads** — не наш стек;
переносить только принципы: слои, схемы, контракты, изоляция, минимум зависимостей.

### 8. Hard skills 2026 [П]

Programming-Knowledge: структуры данных, типы, модульность, полиморфизм, композиция,
декомпозиция, границы/интерфейсы, DI/IoC, coupling/cohesion, иммутабельность, идемпотентность,
тесты, DSL/интерпретатор/AST, контракты, асинхронность, разделение system/app, AI-assisted
engineering. При этом всё это — не более ~30% фокуса инженера в 2026.

## Ноутбук + телефон: что добавлено к первому проходу [Ч]

Прошлые локальные сводки дают более конкретную механику, чем новые посты:

- **Architectural DSL** (`0GZ`): DSL описывает event flows, слои/связность, DI/IoC, потоки
  данных, БД, серверы, routing, permissions; синтаксис JS/TS/Lisp/Markdown → одна
  декларативная структура; интерпретатор бутстрапит приложение. Дополнительно: **executable
  specs as Markdown/JSON**, **architectural tests/spec-as-test**, **tech map** (спека ↔
  файлы/функции), **interface/layer boundary linters**, ownership архитектуры человеком.
- **Три контура** (`qNA`): системный/платформенный код → платформа → продукт; нижние слои
  переиспользуются, по автору код продукта уменьшается **на несколько порядков** (вторичная
  сводка 5–10× — оценка [Ч], не факт); AI ограничивают структурами
  (Record/ConsList — JS-специфика), связь модулей через API/события, а не shared data;
  декомпозиция экономит токены; читать весь AI-код.
- **reslop / review** (`T90`): ревью только hunks, skills из повторяющегося фидбека,
  структурированный фидбек (block_id/start/end line), отдельные refactoring sessions,
  package.json+lock review, test output reduction (`testr`/`t`), incremental commits;
  телефон добавляет: **12 агентов через ACP** (OpenCode/Claude/Codex/Cursor/worktrees).
- **Metarhia** (`KSnSy`): Global Storage, Metacom (transport-agnostic RPC), Sync Engine,
  Service Worker frontend-for-backend, схемы/метасхема, LLM как «спящий агент» с issue→PR,
  цепочка AI-ревьюеров; это сильный контур 1–2, но Node/Postgres/threads — не наш стек.
- **AI-горизонт** (`17Rq`): читать зависимости/минимизировать, архитектура по горизонтали
  (слои) и вертикали (фича-слайсы), не абстрагировать СУБД, PWA/service workers, отключать
  автокомплит, AI не заменяет архитектурное мышление.
- **Телефон** (`2970`): Telegram — инженерная школа, принципы > инструменты; AI силён в
  реализации/проектировании, слабее в обобщении/изобретении; reslop 12 агентов ACP;
  NextTick ~$50/мес, Metarhia Patreon ~$10/мес; часть постов — промо.

### Противоречия/что не считать фактом

- «AI бесполезен для системного кода» vs «агенты пишут системный код в RLO» — контекст
  разный; не разрешаем без отдельного эксперимента.
- Тяжёлый исполняемый DSL vs лёгкие Markdown-спеки — для нашего масштаба сейчас ближе
  contract+tests, полный DSL не оправдан без ADR.
- reslop как инструмент ранее отклонён; берём идеи (hunks, skills, testr), не Node-TUI.
- YouTube/Telegram-метрики/цены — вторичны, могут меняться; телефонные данные `[Ч]`.


## Сопоставление с нашим подходом

| Наш элемент | Тезис Шемсединова | Статус |
|---|---|---|
| `spec/ARCHITECTURE.md` как источник истины | документация/ADR — вход AI | **совпадает** |
| `continue.md`, handoff, контекст-файлы | контекст в артефактах, не в чате | **совпадает** |
| `contract_baseline.json`, `contract_delta`, тесты | контракты/схемы как ограничения | **совпадает, но нет DSL** |
| Phase A/B/C, gated fixes | контуры сужают решения | **частично**: у нас фазы, не три контура |
| LLM-шов инжектируемый, offline core | разделение system/app, изоляция | **совпадает** |
| «Не гонять пустые итерации» | empty loop/Ralph | **дословно совпадает** |
| Минимум зависимостей, pip-audit/CI | dependency checklist | **частично** |
| Import-boundary CLI → advisor.integration | архитектурные границы | **начато** |
| `compact_run.py` | testr/`t`: сжатый вывод тестов | **идея уже есть** |
| `agentrouter_review`/review.py | reslop: hunks, skills, structured feedback | **частично; reslop не внедряем** |
| Tech map/arch tests | спека ↔ файлы; architectural tests | **нет, P3** |

## Что применить (предложения, без кода сейчас)

1. **Карта контуров** в `spec/ARCHITECTURE.md`: (1) core/runtime — store/categorize/security;
   (2) reusable — advisor/PWA/capture; (3) product — UI/rules/config. Явно указать, что
   контур 1 меняется только с contract+bump.
2. **ADR index** (`spec/ADR/` или `docs/decisions.md`) — короткие решения с датой/контекстом;
   AI читает их вместо истории чата.
3. **Расширить import-boundary** с CLI на PWA/integration: static AST test для новых consumer-
   модулей; `advisor.integration` — единственный seam.
4. **Tech map + architectural tests** (P3): таблица «раздел спеки ↔ файлы/функции»; тесты
   границ слоёв/DI; наш `contract_delta` — первый шаг, не полный DSL.
5. **Empty-loop gate**: перед новой итерацией требовать новую вводную (лог/тест/замечание);
   если сигнатура падений не меняется — STOP (уже есть правило, можно автоматизировать в
   preflight).
6. **Dependency review**: lockfile + pip-audit уже в CI; добавить `--min-release-age`-аналог
   для Python (cooldown) — обсудить, не ломает ли uv.
7. **Refactoring sessions + skills**: отдельный слот от фич; повторяющийся фидбек — в skill/
   правило; не строить свой RLO/reslop.
8. **AI-generated code gates**: текущие pytest/ruff/contract/ratchet — соответствуют; добавить
   secret scanning в локальный pre-commit? Уже gitleaks CI.
9. **Не копировать Metarhia/Node/DSL** в spend-tracker: наш масштаб/стек другие; брать принципы,
   не инфраструктуру.

## Secondary findings (phone scan) [Ч]

- **reslop** — ACP-оркестратор на 12 агентов (OpenCode/Claude/Codex/Cursor, worktrees);
  не внедрять без отдельного ADR/аудита. В наших терминах это сильный «второй контур»,
  но цена/риски неизвестны.
- **NextTick / Metarhia** — платное обучение/community; отдельное решение owner, не сейчас.
- Эти пункты не проверены первоисточниками в этом ресёрче; confidence [Ч].

## Abacus Opus 5.5

Owner разрешил использовать для спорных моментов. **Не использовал:** нет текущего
web-сеанса/биллинга; спорные тезисы (AI vs system code, DSL vs Markdown) помечены как
открытые, а не факты. Кредиты не тратил.

## Что проверить вручную

- [ ] Посмотреть `75O83pLvGnc`, `0GZ-Nf8yHEw`, `bedsdFbhqhw`; выписать точные тезисы DSL
      (какой синтаксис, что именно генерируется, как проверяется соответствие).
- [ ] Проверить `tshemsedinov/reslop` (read-only): безопасность, ACP, лицензия; не ставить.
- [ ] Проверить архив `vibecoding/out/0GZ...`, `qNA...`, `T90...` на первоисточники/даты;
      это AI-сводки, не транскрипты.
- [ ] Telegram/NextTick/Metarhia цены и принадлежность канала; телефонный срез `[Ч]`.
- [ ] Подтвердить дату/полноту поста «Трёхконтурная разработка» (2026-07-19).
- [ ] Уточнить у owner, что значит «по Нашему подходу»: сравнение с нашим spec-first или
      применение его метода к нашему проекту.

## Confidence

- [П] primary (авторский GitHub/доки): три контура, empty loop, complexity, dependency checklist,
  Metarhia, hard skills.
- [Ч] YouTube-названия/сниппеты + локальные AI-сводки `vibecoding/out` + телефонный скан:
  Architectural DSL, reslop, NextTick, Telegram-метрики.
- [?] точная механика Architectural DSL и её применимость к Python/FastAPI — не проверена.
