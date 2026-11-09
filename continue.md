# Continue.md — состояние проекта Spendtrack

Обновляется после крупных решений (состояние живёт в файле, а не в истории диалога). Здесь — активный срез:
статус, работа, открытые решения. Полная посессионная история — в приватном архиве
`D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (progressive disclosure; выносы 24.09 и 16.10).
Бюджет файла — гейт `agent_context_audit.py` (WARN 400 стр / 60 КБ; держим заметно ниже, без «осадка»).

## 09.11.2026 (`/capture` review adjudication; same-payload replay fix; remote gate)
- Review adjudicated by code facts: `CAP-01` Host-as-remote-marker accepted and **deferred to
  live Tailscale gate**; `CAP-02` sessionStorage/XSS rejected as P1 (strict CSP + escaped
  descriptions already tested); `CAP-03` accepted and fixed; `CAP-04` deferred (token-gated,
  single-owner); `CAP-05` rejected (backup/restore drill already implemented).
  Artifact: `D:\dev\docs\machine\agentrouter_review\2026-11-09-capture-security\ADJUDICATION.md`.
- Fix `CAP-03`: same `client_id` + same normalized payload now replays **200 with the same
  `tx_id`**/«Уже добавлено», different payload remains **409**; replay checked before
  categorization so no duplicate LLM call. Tests: same-payload JSON replay, no reclassify,
  concurrent same payload; full **1288 passed, 1 skipped**, ruff/contract ok.
  No push/live/DB/UI. Remote pilot still blocked on `CAP-01` live Host-spoof test + ACL/Funnel
  + `spendtrack backup --drill`.

## 01.11.2026 (Phase C closed; push c4948e9; Abacus canary STOP; next PWA)
- Phase C push confirmed: `origin/main = c4948e9`, local = remote, ahead/behind 0; no force.
  Docs `continue.md` now committed as closeout; worktree clean after commit.
- Abacus canary: Basic 20K; Agent was unused 0/3; one Agent task (High / Opus 5.5,
  general-purpose) cost **614 credits**, charged to monthly plan, **not** the 5K promo.
  5K promo is app-builder only; full review **not** started. Canary PASS with caveats;
  2 Agent tasks / ~14.7K credits remain; no Pro, no app build, no retry.
- Canary findings: AB-CANARY-01 phone↔server topology; AB-CANARY-02 Phase C contract
  freeze; AB-CANARY-03 PWA scope. S1 (no sync engine) accept; S2 (no Telegram bridge)
  reject — bridge already exists. First PWA slice: one screen, thin client, **no offline
  queue**; queue is a separate later ticket after ADR + exactly-once test.
- Next priority: PWA quick-capture ADR/spec/test plan; deferred D-22..D-30 / D-32–D-34 /
  D-36–D-39 triage; no new Abacus spend, no AgentRouter POST. Live/DB/UI untouched.
- **Backlog (owner 01.11):** remote CI `docker-smoke` and `lint-and-test` failing. Local fix
  `6519632`: msgpack 1.2.2 CVE → 1.2.4; Dockerfile sets `SPENDTRACK_ALLOW_INSECURE_LAN=1`
  (container isolated, host publishes 127.0.0.1). Docker local not verified (daemon down);
  verify after push. No live.
- **01.11 security/PWA local commits:** `ceec703` (capture static page, trusted hosts, CLI guard)
  + `147ba68` (path isolation, rate limit, `/capture` route, optional `client_id`)
  + `88a6383` (remote app-token, page UUID client_id)
  + `dbb1a3a` (strict client_id: `capture_idempotency`, 409/no second row)
  + `c33edad` (atomic insert-first reservation + rollback; concurrent test)
  + `d9dbe17` (rollback/deleted reservation on add exception/None; failure-injection tests)
  + `4422f8f` (Phase C contract v1: `AdvisorProtocol`, `TemplateAdvisor`, `run_advisor_flow`,
  stub/signature tests). Tests **1277** / ruff clean; contract DRIFT — new `/capture`, `client_id`,
  `capture_idempotency`, contract v1, plus previously accepted `known_tokens`; baseline **updated**
  by owner `/careful` (schema 79 / api 439 / routes 39; `contract_delta check` ok) and committed
  `1f112fb`; `continue.md` still uncommitted.
  Auth =
  Tailscale ACL + required `SPENDTRACK_CAPTURE_TOKEN` (remote POST); `/`/`/approve` remote → 403,
  `/capture` → 200; no offline/SW; API no-store. Live 8766 static page smoked; app code **not
  restarted**, Tailscale not configured. **Pushed**: origin/main = `1f112fb`, local=remote.
- **PWA spec/coverage:** `spec/PWA_CAPTURE.md` — scope/security/deploy, coverage matrix,
  known gaps; PWA/offline/service worker explicitly deferred. Local commits `91b19b1`
  (`docs(pwa): capture spec...`) + `2278b7a` (clarify client_id/busy retry/import boundary);
  now pushed in `1f112fb`. Browser e2e `3dbade3` (local, not pushed): hidden client_id submit,
  reservation row=1, UUID rotation; e2e 1 passed. Test/coverage commit `66c3776`: e2e CI/doc,
  graceful skip, branch coverage API 79% / security 96%, contract `__all__` surface.
  `fa7233f`: CI e2e fails if browser missing; import-boundary limitation documented.
  `969b8be`: CLI uses `advisor.integration` facade; static AST test blocks direct facts/slots/llm
  imports. Local `e212294`: top-100 boundary + compare provenance. Local `84271c8`: compact
  «топ5» regex fix. Local `e0c8514`: conservative alias ambiguity + empty-current compare.
  Full **1286**, contract check ok. Deferred triage — D-36/D-39/D-37 fixed; allow-list P3 open.

## 31.10.2026 (Phase C v2/v3 close; commit c4948e9; push confirmed)
- Phase C v2/v3 accepted fixes applied: **commit `c4948e9`** — `fix(advisor): apply accepted
  v2/v3 fixes (D-15..D-21, D-31, D-35, D-43..D-46)`; 8 files, +226/−23; worktree clean.
- Tests: **1260 full / 101 advisor**, ruff clean; `contract_delta` — only accepted `known_tokens`
  DRIFT; phone patch review PASS (clean-base apply, py_compile, 6/6 targeted tests).
- Canonical findings: 1 P1 + 5 P2 accepted; fixed D-15..D-21, D-31, D-35, D-43..D-46.
  Deferred D-22..D-30, D-32–D-34, D-36–D-39; rejected/unreachable D-40–D-42 untouched.
- Astra v3: 4 STOP (part2 upstream/truncated; package defect fixed); **Astra не ретраить**;
  Sol canonical; no new AgentRouter POST. Sol v3: slots/answer/llm-cli 3/3 OK.
- Push: **confirmed** — `origin/main = c4948e9`, local = remote, ahead/behind 0; no force.
  `continue.md` closeout committed 01.11.
- Next priority: (1) push confirmed; (2) triage deferred/backlog; (3) docs/Phase C closed;
  (4) next product wave (PWA quick-capture, one screen, thin client); new AgentRouter batch
  only by owner scope. Live/DB/UI untouched.

## 28.10.2026 (Phase C implementation + AgentRouter review package)
- Phase C C1–C5 offline: commit `a75211f` (facts/slots/answer/llm + `spendtrack ask`), **72 advisor tests**
  / 1231 suite, ruff clean; live v1.2.5 unchanged; v1.2.6 offline.
- AgentRouter review requests prepared: `D:\dev\docs\machine\agentrouter_review\2026-10-28-phasec-impl`
  (3 canonical packets: facts/allow-list, slots+templates, LLM/CLI; plus a derived combined prompt).
  Exclusions: Opus design P1/P2 (spec v2), bridge v1.2.6/autostart, live LLM, optional slot fallback;
  phone's 2 lean drafts reconciled as reference (no parallel POST).
- Owner menu **2293**: sol primary, canary → one heavy combined POST; astra no. **Canary 28.10 15:55
  timed out** (`ReadTimeout` 300 s, HTTP none, usage `{}`, chars 0, no out); **heavy not sent**, no
  retry/fallback; `BLOCKED`; result `...\2026-10-28-phasec-impl\RESULT.md`.
- Owner menu **2297**: astra burst; canary astra **ok** (HTTP 200, 4 s, 2 chars, usage 14/26/40);
  heavy `prompt_llm_cli.md` (PC-3-LLM-CLI, 38,885 B; combined 130 KB over 110 KB input hard, not
  sent) → HTTP 200 + in-stream `rate_limit_exceeded`, 2 s, chars 0, usage `{}`, no out; **STOP**,
  no retry/fallback, sol not launched; `ack` read.mark=2299.
- Owner menu **2302**: split into 7 self-contained parts (facts 3 / slots 2 / LLM-CLI 2; 18.6–28.1 KB);
  canary 16:06 reused, 3-min gap. Part 1 `01_llm_a` **ok, FIX-FIRST** (input 8,013; output 15,194;
  387 s; chars 5,498); part 2 `02_llm_b` HTTP 200 + in-stream `rate_limit_exceeded` (8 s, 0 chars);
  **STOP**, parts 03–07 not sent; `ack` 2303; details `...\RESULT.md`, `split/`.
- Part 1 adjudication (phone 16:30): **accept 5/5**, reject 0; fixes offline in order P1-11 → P1-03 →
  P1-12a → P2; copied to `ADJUDICATION_part1.md` (sha `0af24026…`); **no code/POST**; owner menu
  pending (fix offline / fix+arm 22:00 / pause).
- Owner menu **2312**: fix part 1 offline — **applied all 5** in `advisor/llm.py` + tests; 23 LLM /
  **85 advisor** / **1244 full** passed; ruff clean; patch `part1_fixes.patch`. Residual:
  `contract_delta` **DRIFT** (`known_tokens` default `()` → `None`); baseline snapshot blocked by
  safety-gate (owner `/careful`); no commit/push/live/POST. Parts 02–07 unreviewed.
- Owner menu **2317** accepted the delta; snapshot retried and **still blocked** by safety-gate
  (`/careful`); baseline unchanged (sha `CF53327E…`); `CONTRACT_DELTA_REPORT.md`; 1244 full / 85
  advisor passed, ruff clean.
- Owner menu **2324**: **leave DRIFT deliberately**; baseline untouched; no snapshot; **Part 1 closed**;
  parts 02–07 unreviewed; addendum `ADJUDICATION_part1_owner.md`; no new POST.
- Owner **20:58**: continue AgentRouter; **armed 22:00 MSK** for parts 02–07 (6 POSTs), canary once,
  180 s gap, attempts=1, no retry/fallback/sol; stop on first failure. Part 02 refreshed with post-fix
  tests; `out/arm2200_status.json`; no commit.
- Arm 22:00: canary ok; **part 02 GO** (input 7,553; output 13,299; 375 s; chars 4,236; 2 P2:
  `--month`/`ask_back`, empty `--month`); **part 03 ReadTimeout** (~24.5 min, no out); parts 04–07
  not sent; 3 POSTs; no retry/fallback/sol; no code/live/LLM/DB.
- Part 02 adjudication: **accept 2 P2**, defer `REG-PC-D-13`; `ADJUDICATION_part2.md` (sha
  `0976144a…`); no code/POST; owner menu pending (fix offline / defer / pause).
- Part 2 P2 fixes (menu 2347): **2/2 applied**; `_parse_slots(..., period_override)` private helper
  (public signature unchanged); empty `--month` exit 2 before store; **87 advisor / 1246 full**,
  ruff clean; patch `part2_fixes.patch`; D-13 deferred; no commit/live/POST.
- Next: owner decision on a new slot/retry or a different channel → then adjudicate (`ADJUDICATION.md`,
  red test first); live LLM wiring not started; v1.2.6 deploy not requested.

## 27.10.2026 (bridge v1.2.5 live; close v1.2)
- Laptop: oc-tg `d7caa0f5` + relay `12c045cb` (v1.2.5) live, relay PID 9852; paged 11 + legacy 3 live PASS.
- Phone: v1.2.2 live (watch 19500 / `de685912`); daemon 13537 / serve 24786 untouched; partner-only ACK silent.
- Wire cross-check v1.2.3<->v1.2.1 PASS; protocol addendum in `D:\dev\docs\machine\MULTI_CHOICE_PROTOCOL.md`.
- Bootstrap repo pushed: `1dce48a..2f20dfd` (`b54ef51` bridge, `47c5846` watch, `2f20dfd` abacus); worktree clean.
- v1.2.6 offline: dead `PAGINATION_ENABLED` removed + tests updated (not deployed; live stays v1.2.5).
- Pending: owner stale tap on menu 2061; Phase C (LLM advisor) next product step; real approval drill; docs commit.

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
