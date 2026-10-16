# Continue.md — состояние проекта Spendtrack

Обновляется после крупных решений (состояние живёт в файле, а не в истории диалога). Здесь — активный срез:
статус, работа, открытые решения. Полная посессионная история — в приватном архиве
`D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (progressive disclosure; выносы 24.09 и 16.10).
Бюджет файла — гейт `agent_context_audit.py` (WARN 400 стр / 60 КБ; держим заметно ниже, без «осадка»).

## Статус (обновлено 16.10.2026)
- Проект: трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx + Tailwind (offline-first ядро,
  LLM-шов только для остатка). Репозиторий: `D:\dev\personal\spend-tracker` (public,
  https://github.com/ExNihil14/spend-tracker). Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- Код: HEAD `677ec61` (wave13 S4/S9: «Счёт/Счет» + инвариант дат; контур 1038 passed) — **ahead origin/main
  на 1**. Сервисы: прод NSSM `spendtrack` 8766; демо-стенд 8799.
- Контур: pytest + ruff + `contract_delta` + `ratchet` + `cc_ratchet` + `build_css`; канон — `spec/PIPELINE.md`,
  `spec/TESTING.md`, `spec/ARCHITECTURE.md`; словарь терминов — `CONTEXT.md`.
- Дизайн: ребрендинг v2 «Стикербук» — направление принято (`DESIGN_DIRECTION_V2_2026-09-29.md`); Wave 0/1
  закоммичены; 3D-графики отклонены (искажают значения).

## Что активно / в работе (срез)
- **Wave13 (AgentRouter-ревью): адъюдикация закрыта 15–16.10** (сводки `ADJUDICATION_WAVE13_SUMMARY_2026-10-16.md`,
  `ADJUDICATION_WAVE13_SUMMARY_FB_2026-10-16.md`). **Ждут решений владельца:** C1/C2/C3 csv_import (суммы /
  односторонние формы / режим ширины), матчер (границы слова), ЕРИП-контракт, политика egress, форма
  пиннинга установщика. После решений — волны правок TDD (порядок — §3 сводок). Окно 02:00 UTC 17.10
  доберёт `bootgate`/`bootgen13`/`bootfixes` (fb-полоса, стриминг SSE).
- **Bootstrap-контур:** `bootscripts_tail_test.py` — красный (K1-фолбэк на боевой verify; 16.10);
  popups C1 + «тихий» N1; boottail-тесты (SEEN-фикс, E/F-подмена, K1) — правки в очереди волн.
- **Прочие открытые:** B-19 (spend_misc C1 — Origin `*.app.github.dev`), B-14 (session_v2 миграция),
  B-22/B-27 (bootstrap-скрипты), fb_c-остаток; PR #6 (setup-uv) — open, решение владельца;
  push: незапушенные коммиты есть (spend/bootstrap) — по команде.
- **Очередь применения (процессное):** `RECOMMENDATIONS_APPLY_QUEUE_2026-09-24.md` §F; канонизация
  continue.md — выполнена 16.10 (этот файл).

## Последние сессии (сжато)
- **16.10 (контур ревью):** окно 11:00 UTC — доставлены `spend_docs` 4/4, `bootpopups` 2/2, `boottail` 2/2;
  SSE-стриминг в `agentrouter_chat.py` починил 504-класс (не-стрим умирал на ~187 с); адъюдикация fb-частей
  закрыта (7 отчётов); канонизация этого файла (история → архив). Детали — `HANDOFF_2026-10-16.md`.
- **13→14.10 (агентская ночь, спенд-сторона):** код spend НЕ менялся (репо чист, `1aa5466`); контур прогонялся:
  979 unit + 101 e2e + ruff + contract_delta + ratchet + cc_ratchet + build_css — зелёные. Долг: **B-19 —
  spend_misc C1**: Origin-проверка доверяет всему `*.app.github.dev` (адъюдикация wave9 P4; эксплуатация
  условна — порт по умолчанию приватный); фикс — сузить до своего host/неймспейса + красный pytest. Смежное:
  `cleanup-opencode-global.py` (v1-эпохи против v2-БД — fail-closed), миграция `session_v2` + C1/C2 — B-14.
- Более ранние сессии (24.09–07.10, волны wave1–wave7) — в `SESSION_HISTORY.md`, разделы `[архив]` (перенос 16.10).

## Архитектурные решения (frozen)
- Ключевые решения и список «не менять без ревью» — `AGENTS.md` §«Ключевые решения» и `spec/ARCHITECTURE.md`
  (единственный источник; здесь не дублируем).

## Git-процесс
- Правила — `AGENTS.md` §«Git-процесс» (trunk-based; commit/push — только по явной команде юзера).
- Публичный репо, `main` защищён; история перезаписана 23.09 (`git-filter-repo`, старый e-mail вычищен).
- 24.09 и 16.10: посессионная история вынесена из публичного файла в приватный архив (указатель в шапке).

## Известные ограничения/грабли
- Правка юзера → merchant_cache + few-shot (правит будущий импорт).
- Не запускать qwen 7b одновременно с dev-сервером (GTX 1050 4GB).
- «Готово» без фактической проверки не принимается: diff/запуск/UI — факт, а не отчёт.
- Демо-стенд 8799 — только с `SPENDTRACK_DB_PATH=data/demo.db` (иначе молча прод-БД; см. скилл verify-spendtrack).
- Инженерные грабли/уроки — единый источник: `spec/PIPELINE.md`, `spec/TESTING.md`, `spec/ARCHITECTURE.md`.

## Возврат к работе
- Прочитай: `AGENTS.md` → этот файл → `CONTEXT.md` → `spec/` (по задаче); контур-сессия — `HANDOFF_2026-10-16.md`.
- Фиксация сессии: `D:\dev\docs\machine\AGENT_ENVIRONMENT_PLAN.md` + Serena `spend-tracker/session-state`.
