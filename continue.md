# Continue.md — состояние проекта Spendtrack

Обновляется после крупных решений (состояние живёт в файле, а не в истории диалога). Здесь — активный срез:
статус, работа, открытые решения. Полная посессионная история — в приватном архиве
`D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (progressive disclosure; выносы 24.09 и 16.10).
Бюджет файла — гейт `agent_context_audit.py` (WARN 400 стр / 60 КБ; держим заметно ниже, без «осадка»).

## Срез 25.10.2026 (privacy finish)
- HEAD `ba8111c`; origin/main `01d0af2`; **ahead 3** (`9a5630b` deps, `af6e9fb` privacy P1,
  `ba8111c` privacy P2) — push только по команде владельца. Bootstrap `1dce48a` уже на origin.
- Privacy P1/P2 done: force-redact loopback shims/remote, opt-out только direct Ollama,
  guarded LLM path, PII до truncate, sanitized logs; **1159 passed**, ruff/contract ok; LLM off.
- Bridge: relay v1.1 live PID 2284 cursor 1799; multi v1.1 live PASS both/unfrozen;
  phone watch 13824 / daemon 13537 / serve 24786 / hb v3. Real once/reject drill — next real approval.
- Open: menu 1866 (`Reaction fix live` / `Push deps` / `AGENTS docs commit` / `Пауза`);
  `AGENTS.md` inline-menu rule committed `a7e0511` (no push); Dependabot rescan after push; Termux:Boot WARN,
  ZCode blocked, Kimi heavy 524. Handoff: `C:\Users\HP\AppData\Local\Temp\opencode\HANDOFF_2026-10-25_spendtrack.md`.
- 25.10 16:15 (laptop preflight): меню 1866 закрыто телефоном (`Reaction fix live` → watch 18875,
  snapshot 153556); laptop-ветки `Push deps`/`AGENTS docs` не выбраны → пауза. Laptop live не тронут
  (relay 2284 / daemon 13080 / responder 13128), approvals pending 0, LLM off; Go usage WARN.
- 25.10 16:26 (owner `#both` sync): `bridge-ui-choice` закрыт — binding `message_id` + кейс 891
  в `test_choice_relay.py`, bridge offline 5/5; push deps — меню 1875 (телефон), AGENTS commit — по tap.
- 25.10 16:36 (owner tap 1875): docs commit без push — `a7e0511` AGENTS (inline-menu), этот срез
  continue; tree clean; pytest 1159 passed (96.9 s), ruff/contract/audit ok. Push deps — отдельно.

## Статус (обновлено 23.10.2026)
- Проект: трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx + Tailwind (offline-first ядро,
  LLM-шов только для остатка). Репозиторий: `D:\dev\personal\spend-tracker` (public,
  https://github.com/ExNihil14/spend-tracker). Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- Код: HEAD — docs-коммит поверх `ff19371` (матчер правил: границы слова + `*`-шаблоны) и `8c2b5e1`
  (wave13 A1/A3/A4/A5), origin/main = `eb8adad` → **ahead 5, push не делался** (только по команде владельца).
  21.10 закоммичено:
  privacy pack (egress-redaction + doctor count-only, `--details` → `key:<sha1[:8]>`), батч телефона
  (A1 `merchant_keys`, A3 few-shot cap после фильтра, A4/A5 PII-стебли в anonymize) и матчер правил
  (слово целиком, `*`-шаблоны, ё→е; +34 теста). Baseline контракта — 76/400/38.
  Сервисы (ноутбук): прод NSSM `spendtrack` 8766 (pid 4752), демо 8799 (pid 3752, demo.db 350 tx) — на `ff19371`
  (перезапущены 21.10 после матчера; live-прогон `/settings/test` и preview — без регрессий).
  **Пересечение 21.10:** ноутбук закоммитил privacy pack (`doctor` по умолчанию без сырых
  описаний/мерчантов, полный текст — `doctor --details`; `redact.py` перед LLM, opt-out
  `SPENDTRACK_LLM_REDACT=0`). Коммиты `e5ec937` + `0b1d9ba`, push не делал. Наш A1 адаптирован к `merchant_keys`; phone batch ребейзнут поверх.
  **Egress-redaction — по msg 773 владелец выбрал пакет (egress-only: description/merchant/few-shot;
  store/кэш не трогаем; opt-out `SPENDTRACK_LLM_REDACT=0`).** Privacy pack закоммичен ноутбуком
  (`e5ec937` + chore `0b1d9ba`, push не делал); phone A1/A3/A4/A5 ребейзнут поверх в `/tmp/opencode/st-final`;
  `redact.py`, `test_doctor_privacy.py`, `test_llm_redaction.py` на месте. Финальный ребейз: **1104 passed**
  (101 e2e deselected, 284.12 с); docs/contract 23, ruff/ratchet/cc ok, contract snapshot 76/396/38;
  commit/push — только по слову владельца.
- **23.10 (Abacus privacy P0/P1, commit `5e54635` в `fix/privacy-p0-p1`; push pending):** `redact.py` — 20-значные счета РФ (`[CARD]`),
  телефоны `7916…`/`916…` без `+`/`8`, Unicode-пробелы (NBSP/narrow/thin) в картах/счетах/IBAN;
  `llm.py` — forced redaction для удалённых провайдеров (`SPENDTRACK_LLM_REDACT=0` только локально);
  `categorize.py` — алиасы категорий (`Groceries`→`groceries`) и redaction DEBUG-описания. Тесты red→green:
  **1145 passed**, ruff/contract/cc ok; commit — в этой ветке, push не делался. Источник — `abacus_review/2026-10-23/ADJUDICATION.md`.
  Relay P0-1 (per-chat inbox cursor) — applied + live в bootstrap (`approval-relay.py`), PID 10960
  с 24.10 01:57, state `inbox_cursors`; тесты 37/37; restart не требуется. Остальные relay P0/P1 — отдельный тикет; owner-only
  config (tool_output/compaction/arch-reviewer) — за владельцем.
- Контур: pytest **1138 passed** (101 e2e deselected; 1104 + 34 матчера) + ruff +
  `contract_delta` (snapshot 76/400/38) + `ratchet` + `cc_ratchet` + `build_css --check` — зелёные 21.10.
  Канон — `spec/PIPELINE.md`, `spec/TESTING.md`, `spec/ARCHITECTURE.md`;
  словарь терминов — `CONTEXT.md`.
- Дизайн: ребрендинг v2 «Стикербук» — направление принято (`DESIGN_DIRECTION_V2_2026-09-29.md`); Wave 0/1
  закоммичены; 3D-графики отклонены (искажают значения).

## Что активно / в работе (срез)
- **Wave13 (AgentRouter-ревью): адъюдикация закрыта 15–16.10** (сводки `ADJUDICATION_WAVE13_SUMMARY_2026-10-16.md`,
  `ADJUDICATION_WAVE13_SUMMARY_FB_2026-10-16.md`). **C1/C2/C3 csv_import — реализованы 16.10** (TDD, `a7e9cad`).
  **Решения-независимый срез волны A (②+④) — реализован 16.10 ночь-2** (TDD, закоммичен `95dc2b8`; см. «Последние сессии»).
  **19.10: пакет `spend_wavea` закоммичен (`dc6bcf3`), сервисы перезапущены; 21.10 docs — `eb8adad`.**
  **21.10 — follow-up wave13 (закоммичено `8c2b5e1`):** A1 минимизация doctor print (`key:<sha1[:8]>`), A3 cap примеров
  после фильтра таксономии, A4/A5 английские PII-шапки (Card/Name/PAN/IBAN/Holder/Phone/E-mail/Address) + «Ф.И.О.»;
  B2/N1 — уже в `dc6bcf3`, дубль снят. +16 тестов, baseline контракта обновлён. **Матчер правил (границы слова) —
  решён и закоммичен `ff19371`** (слово целиком + явные `*`-шаблоны, ё→е; +34 теста).
  **Ждут решений владельца:** ЕРИП-контракт, форма пиннинга установщика, approve-бейдж.
  Окно 02:00 UTC 17.10 доберёт `bootgate`/`bootgen13`/`bootfixes` (fb-полоса, стриминг SSE).
- **Bootstrap-контур:** волны ⑤⑥ закрыты 16.10 вечером — `bootscripts_tail_test.py` 12/12
  (K1-герметичность: копия cmd без абсолютного фолбэка; SEEN; N4) и `agentrouter_probe_test.py` 6/6
  (E/F наблюдают журнал фейка, fail-closed); popups v3 (C1/N1/S1/S5/S2) + тест 27/27; habr-C2-матчер 26/26.
  bootstrap закоммичен и запушен (`a8bfd4c`, `f63e9ce`). Остаток ⑦ (дизайн): изоляция зелёной ветки
  генераторов (Н1), S-пункты `test_make_wave578_parts.py`, O1 `popups.cmd`.
- **23.10 (Abacus Opus 5.5, privacy review):** P0 **латентные** дыры redaction — 20-значные счета РФ и
  телефоны `7916…`/`916…` без `+`/`8` не маскируются; P1 — NBSP/IBAN, global opt-out для cloud.
  LLM сейчас **off** (`llm-status`), утечки нет; фикс — отдельным TDD-пакетом по команде (тесты:
  `test_llm_redaction` + `build_user_prompt`/few-shot). Разбор — `abacus_review/2026-10-23/SUMMARY.md`.
- **Прочие открытые:** B-14 (session_v2 миграция), B-22/B-27 (bootstrap-скрипты), fb_c-остаток;
  PR #6 (setup-uv) — open, решение владельца; push: spend — **ahead 5** (feature `ff19371` + docs), по команде;
  bootstrap — чисто. B-19 (spend_misc C1) — **закрыт 14.10** (`5975660`, сужение Codespaces-Origin до своего пространства).
- **Очередь применения (процессное):** `RECOMMENDATIONS_APPLY_QUEUE_2026-09-24.md` §F; канонизация
  continue.md — выполнена 16.10 (этот файл).

## Последние сессии (сжато)
- **21.10 (матчер правил — выбор владельца «Матчер без push», `ff19371`):** TDD red→green: подстрочный
  поиск ловил бренды внутри чужих слов («ГИПЕРМЕТРО»→transport, «ПЕРЕВОДЧИК»→transfers, «ВБЛИЗИ»→household,
  «МАГНИТНЫЙ ДЕРЖАТЕЛЬ»→groceries). Семантика: слово целиком (Unicode-границы), частичное — только явным `*`
  (`ЗАРАБОТН*` — префикс, `*ТЕСТ` — суффикс, `*ТЕСТ*` — подстрока), ё→е с обеих сторон. Диагностика UI
  (`analyze_rules`/preview/тестер) и `suggest-rules` используют ту же семантику (без ложных «мёртвых»).
  Гейты: pytest **1138**, ruff/contract (аддитивно 396→400)/ratchet/cc/build_css — ok; baseline snapshot 76/400/38.
  Live (прод 8766 / демо 8799 на `ff19371`): `/settings/test` — 4 негатива без совпадений (→ LLM/офлайн),
  «МЕТРО ТУРНИКЕТ»/«ЗАРАБОТНАЯ ПЛАТА»/«ВБ МАРКЕТ»/«ПЯТЕРОЧКА-12» — те же категории; preview: «МЕТРО ТУРНИКЕТ»
  помечен «будет мёртвым» (перекрыт #12), «ГИПЕРМЕТРО 12» — без конфликтов; `/health` 8/350 tx, `/health/data` ok.
- **21.10 (review follow-up wave13, закоммичено `8c2b5e1`; ребейз на `eb8adad`):** TDD red→green по A1/A3/A4/A5:
  doctor detail — только `key:<sha1[:8]>` (сырые description/merchant не печатаются); few-shot лимит 8 —
  после фильтра таксономии; anonymize — английские Card/Name/PAN/IBAN/Holder/Phone/Email/Address и «Ф.И.О.».
  B2/whitespace уже закрыт в `dc6bcf3` (`_cache_key`), наш дубль снят при ребейзе. Сверху наложен
  privacy pack ноутбука (egress `redact.py`, минимизация doctor/`/health/data`, тесты) — combined-контур:
  pytest **1104 passed** (1088 pack + 16 phone; 101 e2e deselected), ruff/contract(snapshot 76/396/38)/
  ratchet/cc — ok; `build_css --check` зелёный после chore `0b1d9ba`.
  Закоммичено `8c2b5e1` (push — только по команде владельца); матчер правил — `ff19371` (см. выше).
  Мост (вне spend): form relay v1.4.7 — `OC-FORM`/`/api/form`, live-тест 5/5; детали — STATE 84.
- **16.10 (ночь-2, волна A — решения-независимый пакет):** TDD red→green по адъюдикациям wave13 (C1/C2/Н-2/Н-6/Н-7,
  HELP1 #1/#2/#4, S7): `LLM_ENV_VARS`=7 (единый источник; тесты/доки опираются на него), PRIVACY «Как выключить»
  + free-матрица (README синхрон), `_EXAMPLES_LIMIT=8`, numbers-sync 300/80/8; anonymize-стемы русских шапок
  (описание/карта/документ/ФИО); `confirm` — rc=2 вне таксономии (до Store); htmx-дубликат — «Не добавлено»+OOB;
  seed кэша по `merchant or description`; doctor live-set с описаниями merchantless. Гейты: pytest **1061**,
  ruff/contract (snapshot `+LLM_ENV_VARS`)/ratchet/cc/build_css — ok; мутации 8/8 (+доктор-перепроверка). Живые факты —
  `%TEMP%\opencode\wave_a_live\report.txt` (confirm rc2/rc0; seed 3 путей; doctor ok; анонимайзер без PII;
  temp-стенд 8767: dup+бейдж, погашен). Закоммичено `95dc2b8` (по команде; трейлер `Contract-Change:`); push — по команде.
- **16.10 (ночь, wave13 C1/C2/C3 csv_import):** принятые решения владельца реализованы TDD (+9 тестов,
  80/80 целевых; подробности — сводки wave13). C1 — строгая форма суммы Приорбанка («1,577.92»/«1577.92»,
  иное → видимый `amount_unparsed`, не тихая сумма); C2 — «Обороты Списание» и «Поступление» — две раздельные
  обязательные колонки (переименование любой → `format_error`); C3 — лишняя ячейка строки priorbank →
  `format_error` (строгий режим только priorbank — Sber-форма с хвостовым `;` не задета, контроль-тест).
  **Закоммичено:** `a7e9cad` (C1/C2/C3 + контракт-snapshot C2). **Флейк rollover** (`test_cli_busy_db_friendly_error`;
  логи тестов писали в боевой `data/logs` при живом NSSM-сервисе) закрыт `9de8186` — журналы приложения
  в тестах в session-tmp + регресс-тест. **Дрейфы контура закрыты:** `27bb02f` (cc_ratchet baseline
  `bench.py::seed` 13→14 — принятый рост B-17 ч.2, Contract-Change), `a2ca962` (css-манифест после `9cbaee1`).
  Full-suite: **2×1048 passed**. Прод 8766 — рестарт на новый код (pid 15252, `/health` ok). Live-факт:
  `%TEMP%\opencode\w13_csvc\` (`live_report.txt` CLI + `http_report.txt` — multipart-импорт на temp-стенде 8767).
  Push — по команде владельца.
- **16.10 (вечер, bootstrap-волны):** B-⑤⑥ + habr-C2: tail-тесты возвращены в зелёное (`bootscripts_tail_test`
  12/12 — K1-герметичность; `agentrouter_probe_test` 6/6 — E/F-журнал, fail-closed rc=99), popups (27/27),
  habr (26/26); стаб-пробы «красные до / зелёные после» + мутационная чувствительность —
  `%TEMP%\opencode\w13_boottail\`; детали — `HANDOFF_2026-10-16.md` §8. bootstrap: `a8bfd4c`+`f63e9ce`
  (запушены). Остаток ⑦ — дизайн-вопросы.
- **16.10 (контур ревью):** окно 11:00 UTC — доставлены `spend_docs` 4/4, `bootpopups` 2/2, `boottail` 2/2;
  SSE-стриминг в `agentrouter_chat.py` починил 504-класс (не-стрим умирал на ~187 с); адъюдикация fb-частей
  закрыта (7 отчётов); канонизация этого файла (история → архив). Детали — `HANDOFF_2026-10-16.md`.
- **13→14.10 (агентская ночь, спенд-сторона):** код spend НЕ менялся (репо чист, `1aa5466`); контур прогонялся:
  979 unit + 101 e2e + ruff + contract_delta + ratchet + cc_ratchet + build_css — зелёные. Долг: **B-19 —
  spend_misc C1**: Origin-проверка доверяет всему `*.app.github.dev` (адъюдикация wave9 P4; эксплуатация
  условна — порт по умолчанию приватный); фикс — сузить до своего host/неймспейса + красный pytest. **[закрыт
  14.10: `5975660`, `FIX_SPEND_MISC_C1_2026-10-14.md` — `_codespace_namespace` + 12 passed]**. Смежное:
  `cleanup-opencode-global.py` (v1-эпохи против v2-БД — fail-closed), миграция `session_v2` + C1/C2 — B-14.
- **19.10 (пакет `spend_wavea` — письмо телефона 0005, одобрение владельца msg 119):** TDD red→green: B2/whitespace закрыт единым модульным `_cache_key` (strip-first + sha1; пустой мерчант остаётся «dead» для doctor — тест сохранён); лукап/seed/bulk/doctor приведены к strip-first. PRIVACY: `ALLOW_LOCAL_LLM` читается из окружения процесса (dotenv не включает — fail-closed). Тест-хардненинг fb_b (7): фенс-парсер секций, off-switch «переменная+инструкция», окно «и/или», merchant-лимиты (landing/help + тест), FREEL-only e2e (`test_llm_byo`), AST-исчерпываемость (`test_offline`), count==1 (`test_api`). Прогон **1071 passed** (+5), ruff/contract ok. **Закоммичен `dc6bcf3`** (11 файлов, +268/−33; pre-commit secrets PASS), **сервисы перезапущены** (8766/8799) — push по команде.
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
