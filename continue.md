# Continue.md — состояние проекта Spendtrack

Обновляется ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга: состояние живёт в файле,
а не в истории диалога). Здесь — только активный срез и последние сессии; полная посессионная история —
в приватном архиве `D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (сплит 24.09.2026 по методологии
progressive disclosure: `D:\dev\docs\machine\RULE_EXTRACTION_PLAN_received_2026-09-24.md`).

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx + Tailwind (offline-first ядро,
  LLM-шов только для остатка). Репозиторий: `D:\dev\personal\spend-tracker` (public,
  https://github.com/ExNihil14/spend-tracker). Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- Контур (24.09): **561 unit + 51 e2e** + ruff + contract-дельта (`scripts/contract_delta.py check`) +
  `build_css --check` — зелёные. Прод NSSM 8766: схема v5, doctor 13/13, LLM off, 8 tx.
- Последнее закоммичено: `36bc0ea` (K2 — `spendtrack backup`/`anonymize` как CLI пакета, README «Обновление
  и удаление»; push — по команде юзера). Перед ним: `afce062` (правки полного аудита), `60dc8ff` (ревью M-4…M-8).
- Волны дизайна M-1…M-8 закрыты; релизные блокеры — K1 (контур) / K3 (тексты + CHANGELOG 0.2.0-beta);
  решения автора (#15, МНС, Boosty) — за юзером.

## Что активно / в работе
> **АКТУАЛЬНО (24.09, K3 закрыт: публичные тексты + CHANGELOG):** README (браузеры/e2e-формулировка,
> `ruff check .` как в CI, EN/названия банков, NSSM-права, FAQ «Обновление/удаление», Docker-предупреждение,
> «Сайт»); лендинг (FAQ «импорт не распознал выписку» + `anonymize`; P1-6 — телеметрия vs `doctor --share`,
> free-opt-in в карточке LLM; минуты — drag&drop-шаг, caption Сбера, «≥ 0.9», Netflix → нейтрально,
> финальный CTA + macOS/Linux); **CHANGELOG `[0.2.0-beta]`** (Added/Changed/Fixed/Security + пометка
> историчности 0.1.0); **SECURITY** — приватный канал (PVR включён фактом), «localhost ≠ один пользователь»,
> BitLocker-заметка убрана; **PRIVACY** — free-цепочка generic; перки-канон выровнен (README/лендинг/
> `supporter.yml`). Первая часть закоммичена (`16f17a2`), K3-часть — в дереве, ждёт коммита.
> Контур: 561 unit + test_landing 11/11 + ruff + contract + build_css — зелёные.
> **АКТУАЛЬНО (24.09, dev-процесс: AI-native SDLC + контекст-аудит):** разобраны playbook Anthropic
> (`RESEARCH_AI_NATIVE_SDLC_PLAYBOOK_2026-09-24.md`) и RULE-EXTRACTION-план; внедрён
> `D:\dev\bootstrap\scripts\agent_context_audit.py` (бюджет/пороги/битые указатели/дубли); экспертиза
> arch-reviewer по открытым вопросам — решения в очереди §F; **посессионная история вынесена в приватный
> архив** (эта правка). Следующее: K3 (тексты + CHANGELOG) или K1 (контур; тег/заморозка — юзер).
> **АКТУАЛЬНО (24.09, сессия «K2-минимум — жизненный цикл данных»): ✅ `spendtrack backup` и `spendtrack anonymize`
> как CLI-команды пакета (deliverable; ждёт команды на коммит).** Логика перенесена из `scripts/` в
> `spendtrack/backup.py`/`spendtrack/anonymize.py` (скрипты — тонкие обёртки; у установок через uv tool их не было);
> `anonymize` — stderr-варнинг «даты/суммы/категории не обезличиваются» + `--rows` (дефолт 5, `0` — все;
> для dev-фикстур явно `--rows 0`); `backup` — прежние `--keep/--copy-to/--force` + суффикс при коллизии
> секунды; общий `console.utf8_stdout()` (stdout И stderr). Попутно закрыты реальные дефекты: CRLF-выписки
> (cp1251) при записи превращались в `\r\r\n` (text-mode Windows) — теперь bytes + регресс-тест; ошибки CLI
> («БД не найдена» и т.п.) унифицированы в stderr; отрицательный `--rows` и конфликт OUT/`-o` — явные ошибки.
> Тексты: README §«Обновление и удаление» (P1-4), единая формула пути к БД в README/PRIVACY/SECURITY +
> таблица команд и `/help` (P1-10, P1-3); прочие публичные хвосты (CHANGELOG/перки/лендинг-мелочи) — волна K3.
> Ревью $0 (gpt-oss:120b, 25 с): 3 приняты, 5 отклонены фактами —
> `EXPERT_REVIEW_K2_DATA_LIFECYCLE_OSS_2026-09-24.md`. Контур: **561 unit + 51 e2e** + ruff + contract
> (snapshot осознанно: +12 аддитивных символов) + build_css; live: temp-CLI (backup/guard/anonymize/обёртки) +
> прод NSSM рестартнут (health/health_data 200, doctor 13/13 OK, `/help` с новыми командами, свежий бэкап).
> Отложено тикетом: автобэкап перед миграцией + `backup --verify` (K2-остаток в RECOMMENDATIONS_APPLY_QUEUE).
> Следующее по очереди: K3 (тексты + CHANGELOG 0.2.0-beta) или K1 (Windows-CI/пиннинг; тег/заморозка — юзер).
> **Закоммичено `36bc0ea` (24.09); push — по команде юзера.**


## Архитектурные решения (frozen)
- Ключевые решения и список «не менять без ревью» — в `AGENTS.md` §«Ключевые решения» и `spec/ARCHITECTURE.md`
  (единственный источник; здесь не дублируем).

## Git-процесс
- Правила — `AGENTS.md` §«Git-процесс» (trunk-based, commit/push только по явной команде юзера); полный
  отчёт — `D:\dev\docs\machine\GIT_WORKFLOW_RECOMMENDATIONS.md`.
- Публичный репо, `main` защищён; история перезаписана 23.09 (`git-filter-repo`, старый e-mail вычищен).
- 24.09: посессионная история вынесена из публичного файла в приватный архив (указатель в шапке).

## Известные ограничения/грабли
- Правка юзера → merchant_cache + few-shot (правит будущий импорт).
- Не запускать qwen 7b одновременно с dev-сервером (GTX 1050 4GB).
- «Готово» без фактической проверки не принимается: diff/запуск/UI — факт, а не отчёт.
- Инженерные грабли и уроки — единый источник: `spec/PIPELINE.md`, `spec/TESTING.md`, `spec/ARCHITECTURE.md`.

## Возврат к работе
- Прочитай: `AGENTS.md` (команды/правила), `CONTEXT.md` (словарь), `spec/` (архитектура/контур), этот файл
  (статус + активный срез). Очередь применения — `D:\dev\docs\machine\RECOMMENDATIONS_APPLY_QUEUE_2026-09-24.md`
  (§F — процессные пункты из AI-native playbook и контекст-аудита). Фиксация сессии —
  `D:\dev\docs\machine\AGENT_ENVIRONMENT_PLAN.md` + Serena `spend-tracker/session-state`.
