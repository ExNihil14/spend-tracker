# Тимур Шемсединов — one-pager для нашего подхода

Дата: 2026-11-01. Research only; код/live не трогал. Полный разбор:
`RESEARCH_TIMUR_SHEMSEDINOV_2026-11-01.md`.

## Вердикт

**Принципы > инструменты.** Его сильные тезисы совпадают с нашим spec-first/phase-gated
подходом; инфраструктуру Metarhia/reslop не копируем. Главная польза — явные ограничения
для AI, документация как вход, борьба со сложностью и empty-loop-дисциплина.

## 7 тезисов

1. **Три контура** [П]: технологический стек → параметризованные модули → продукт. Каждый
   следующий сужает решения; AI эффективен внутри подготовленных ограничений; по автору код
   продукта уменьшается **на несколько порядков** (вторичная сводка 5–10× — оценка [Ч], не факт).
2. **Empty loop** [П]: итерация без новой вводной усиливает ошибки; первый проход — полный,
   следующий — только с обратной связью/ограничением.
3. **Документация/ADR/contracts** [П]: AI читает markdown/спеки; живая документация — стабильный
   контекст, а не история чата.
4. **Architectural DSL** [Ч]: исполняемая спека (event flows, DI, layers, routing, permissions)
   как single source of truth + architectural tests/tech map. Идея сильная, но для нашего
   масштаба сейчас достаточно contract+tests; полный DSL — только после ADR.
5. **Сложность/LoC** [П]: меньше кода, accidental complexity, разделение system/app, изоляция;
   «соревноваться не кто больше генерирует, а кто меньше с тем же результатом».
6. **Dependencies/supply chain** [П]: lockfile, review, secret scanning, AI-код через
   review/tests/scans, никаких prod-секретов; минимум зависимостей.
7. **reslop/ACP** [Ч]: 12 агентов, worktrees, hunks/skills/structured feedback; **не внедрять**
   без ADR/аудита; брать идеи (компактный diff, skills, testr), не Node-TUI.

## Что уже совпадает с нами

- `spec/ARCHITECTURE` + `continue.md` + handoff = документация/контекст.
- `contract_baseline` + `contract_delta` + pytest/ruff/ratchet = ограничения/arch tests (частично).
- `advisor.integration` + static import test = архитектурная граница.
- `compact_run.py` = идея testr (сжатый вывод тестов).
- «Не гонять пустые итерации» = empty loop.

## Что применить (статус после адъюдикации 09.11)

1. Карта трёх контуров — **внесена** в `spec/ARCHITECTURE.md` как лёгкая tech map.
2. ADR index и отдельная tech map — **не создавать**: дубли существующих спек/`continue.md`.
3. Import-boundary — **перенесён** в `spec/PHASE_C_ADVISOR.md`; PWA не является consumer advisor.
4. Empty-loop gate — **уже есть** в `spec/PIPELINE.md`; новый preflight не строим.
5. Dependency review — **уже есть** (lockfile/pip-audit/Dependabot/SHA actions); cooldown отложен.
6. Отдельные refactoring sessions + skills из повторяющегося фидбека — остаются P3 по потребности.

## Не делать

- Не копировать Metarhia/Node/Postgres/threads.
- Не внедрять reslop/RLO/DSL без ADR и аудита.
- Не платить за NextTick/Metarhia без owner go.
- Не выдавать YouTube/Telegram-сниппеты за проверенные факты.

## Confidence

[П] авторские GitHub/доки; [Ч] YouTube/локальные AI-сводки/телефон; [?] точная механика DSL
и применимость к Python/FastAPI. Abacus Opus 5.5 не использовал: спорные тезисы помечены как
открытые, платного подтверждения не требовалось.
