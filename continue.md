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
> **АКТУАЛЬНО (25.09, §I M10 — ratchet-метрики): ✅ сделано (в репо, ждёт коммита).** `scripts/ratchet.py`
> (temp-БД, прод не трогает): SQL-запросы на `report_month` = **2**, на импорт 100 строк = **435**
> (≈4.35/строку — кандидат в K7), медиана времени правил-категоризации — инфо (вне гейта). Baseline
> `spec/ratchet_baseline.json` — гейт «только вниз» (повышение лишь `snapshot --force`; путь в protected
> paths гейта), CI-шаг «Ratchet metrics» рядом с contract-дельтой; `tests/test_ratchet.py` (3).
> Контур: **598 unit + 52 e2e** + ruff + contract + build_css; ревью $0 — 1 P0+1 P1 приняты, 5 отклонены
> фактами (`EXPERT_REVIEW_RATCHET_OSS_2026-09-25.md`). Далее: §I M11 (contradiction-check), Q6-остаток, S4/S5.
> **АКТУАЛЬНО (25.09, §I M9 + Q6-каркас): ✅ M9 / 🔶 Q6 (dev-tooling, вне репо).** Плагин `skill-log.js`
> (канон bootstrap, копия в `~\.config\opencode\plugins\`; тест `skill_log_test.mjs` — 3 сценария/8 проверок,
> ревью $0 — 1 P1 принят, 6 отклонены фактами) пишет JSONL `D:\dev\docs\machine\metrics\skill-usage.jsonl`
> (ts/skill/session/cwd). `PROCESS_METRICS.md`: precision ревью **14/30 ≈ 47%**, rework **28/174 ≈ 16%**;
> «недотриггер» — из журнала после рестарта; стоимость/CI/уроки — ждут данных. Активация — рестарт opencode.
> **АКТУАЛЬНО (25.09, §I M8+Q5.2 — гейт деструктива/protected paths): ✅ сделано (dev-tooling, вне репо).**
> Плагин `safety-gate.js` (канон `D:\dev\bootstrap\config\plugins\`, копия в `~\.config\opencode\plugins\`):
> `.env`/`spec/contract_baseline.json`/`data/**` — hard-deny для edit/write/multiedit/patch; деструктив
> (force-push/`reset --hard`/`rm -rf`/NSSM remove/…) — только при свежем маркере careful-режима. `/careful`
> (команда + `scripts/careful_gate.mjs`, окно 10 мин); оффлайн-тест `safety_gate_test.mjs` — 4 сценария /
> 29 проверок (+sync канона); ревью $0 ×2 — 3 P0+1 P1 приняты, 2 P0+1 P1 отклонены фактами. Protected-actions —
> в `AGENTS.md` проекта (в дереве, ждёт команды на коммит). Активация гейта и триггеров скиллов — после рестарта opencode.
> **АКТУАЛЬНО (25.09, §I M7 — проектные скиллы): ✅ сделано (в дереве, ждёт коммита).** `.opencode/skills/`:
> `bank-adapter` (маршрут адаптер→фикстура→тест→golden + Gotchas реальных выписок), `release` (K1-контур:
> тег/CHANGELOG/пиннинг/заморозка/Windows-CI), `verify-spendtrack` (DoD-шаг live-прогона: сценарий из diff +
> 2 соседних потока, отчёт без правок). Регресс — `tests/test_skills.py` (7: name=каталог, description,
> Gotchas, живые указатели, авто-дискавери каталогов); указатели — AGENTS.md Layout + `spec/PIPELINE.md`.
> Контур: **595 unit + 52 e2e** + ruff + contract + build_css; ревью $0 (nemotron-3-ultra, 122 с) — 3 P1
> приняты, 2 P0 отклонены фактами (`EXPERT_REVIEW_M7_SKILLS_OSS_2026-09-25.md`). Канон = репо (opencode читает
> `.opencode/skills/` напрямую); срабатывание триггеров — после рестарта opencode. Коммит — по команде юзера.
> **АКТУАЛЬНО (25.09, Q2 — дедуп глобального AGENTS.md): ✅ сделан (dev-процесс, вне репо).** Глобальный
> `AGENTS.md`: 59 стр / ≈1 907 ток (было 86 / ≈3 412, −44%); факты → раздел «СРЕДА» `AGENT_ENVIRONMENT_PLAN.md`,
> роутинг-детали → `MODEL_ROUTING_OPENCODE_GO.md` §14; бэкап —
> `D:\dev\docs\machine\archive\AGENTS_global_2026-09-25_pre-Q2.md`; `agent_context_audit.py` — OK
> (28 указателей, 0 битых). Следующие deliverable: §I M7–M11 (Gotchas-скиллы, лог скиллов, ratchet-метрики,
> contradiction-check), Q5.2 (плагин-гейт protected paths), Q6 (`PROCESS_METRICS.md`), §I-S4/S5.
> AgentRouter-поллер: окно 22:55 UTC → результат в `C:\Users\HP\AppData\Local\Temp\opencode\agentrouter_review\`
> (проверить в начале следующей сессии).
> **АКТУАЛЬНО (25.09, АВАРИЙНЫЙ HANDOFF — сессия падает с 400):** `AI_APICallError: Bad Request`
> (opencode-go/deepseek-v4.1-flash). Факты: изображений нет, сессия переросла (514 сообщений, 4.6 МБ частей,
> компакции не было) → диагноз `D:\dev\docs\machine\OPENCODE_400_DIAGNOSIS_2026-09-25.md`; **дальше работать
> в НОВОЙ сессии по `D:\dev\docs\machine\SESSION_START_PROMPT.md`**. Git: `main` = **`2681a5f`**, ahead 6,
> дерево чистое. §G закрыт целиком (1–7, включая GIF `landing/assets/demo.gif`); §I-S1/S2/S3/S6 применены;
> **Q2 (дедуп глобального AGENTS.md) НЕ начат** — следующий deliverable (план в стартере); затем §I M7–M11,
> Q5.2, Q6 и K1 (тег/заморозка — за юзером). Контур: **588 unit + 52 e2e** + ruff/contract/build_css;
> прод NSSM актуален.
> **АКТУАЛЬНО (25.09, §G-1..3 — регресс-хардненинг):** property-based (`hypothesis`):
> `tests/test_property_parsers.py` (инвариант «любой ввод → запись или `_skip` с причиной; даты в БД только ISO»),
> `tests/test_import_chaos.py` (CR/CRLF/cp1251/битые байты, 20K-описание, лимит, пустышки, случайные байты,
> параллельная UI-запись), фикстуры миграций v3/v4. **Property-тесты нашли 2 реальных дефекта (закрыты):**
> csv падал на одиночном `\r` (нормализация переводов строк); `parse_amount("nan"/"inf")` → контролируемая
> `InvalidOperation` (CLI `add` — exit 1). Контур: **578 unit + 51 e2e** + ruff + contract + build_css;
> ревью $0 — 2 приняты / 8 отклонены фактами (`EXPERT_REVIEW_G_HARDENING_OSS_2026-09-25.md`);
> live: `add nan` → exit 1, CR-выгрузка → `+1 добавлено`. **Закоммичено `2c4c4ce`, прод рестартнут.**
> **§G-4/5 — ✅ закоммичено `33b5966`:** golden-набор `tests/golden/merchants.csv` + `scripts/golden_report.py`
> (read-only, `reports/golden.json`; база 34/34 rule-хитов, 6 нерешённых, 0 ошибок — основа калибровки 0.9),
> конкурентный HTTP-смоук (`test_concurrent_http.py`), e2e жизненного цикла категории. Контур:
> **581 unit + 52 e2e** + ruff + contract + build_css.
> **§G-6 (K6) — ✅ закоммичено `608952d` (+ `1ce6c4f` стабилизация концуррентного теста):** сноска
> «не учтено N операций в валюте» (`report_month`/`digest` + `foreign_transactions_count`; `/`, `/dashboard`,
> CLI `report`; показывается при N>0). Контур: **584 unit + 52 e2e**; ревью $0 — 0 принято / 2 отклонены
> фактами; live-факт на временном стенде.
> **§G-7 (K5-минимум) — ✅ закоммичено `2681a5f`:** GIF «импорт → подтвердить → дайджест»
> (`scripts/record_demo_gif.py`: изолированная копия demo-БД → временный uvicorn → 4 кадра Playwright →
> Pillow-подписи → `landing/assets/demo.gif`, 960px/~272 КБ) + `tests/test_demo_gif.py`, лид-кадр в `#screens`,
> README-ссылка; ревью $0 — 5 принято/2 отклонены (`EXPERT_REVIEW_GIF_DEMO_OSS_2026-09-25.md`).
> Контур: **588 unit + 52 e2e** + ruff + contract; live: лендинг 200, gif 200 `image/gif`.
> **§I (блог claude.dev) — инструкции применены:** `scripts/review.py` (только merge-blocking + «как показать,
> что падает» + неподтверждённое), `REVIEW_CHECKLIST.md`, глобальный `AGENTS.md` (итог «Нужно от тебя/Изменено/
> Найдено» + стоп-правило deliverable-скоупа), skill `research` (метки [П]/[Ч]/[?]). Осталось: §I-S4/S5, M7-M11.
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
