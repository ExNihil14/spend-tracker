# Continue.md — состояние проекта Spendtrack

Обновляется после крупных решений (состояние живёт в файле, а не в истории диалога). Здесь — активный срез:
статус, работа, открытые решения. Полная посессионная история — в приватном архиве
`D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (progressive disclosure; выносы 24.09 и 16.10).
Бюджет файла — гейт `agent_context_audit.py` (WARN 400 стр / 60 КБ; держим заметно ниже, без «осадка»).

## Статус (обновлено 16.10.2026)
- Проект: трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx + Tailwind (offline-first ядро,
  LLM-шов только для остатка). Репозиторий: `D:\dev\personal\spend-tracker` (public,
  https://github.com/ExNihil14/spend-tracker). Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- Код: HEAD `dc6bcf3` (пакет `spend_wavea` — B2/N1 + тест-хардненинг fb_b; 11 файлов, +268/−33) — **ahead origin/main на 1** (push — по команде владельца). Прогон **1071 passed**, ruff/contract ok. Сервисы перезапущены на `dc6bcf3` (19.10): прод NSSM `spendtrack` 8766 (pid 11844, 8 tx), демо-стенд 8799 (pid 504, demo.db 350 tx); `/health` + `/health/data` ok (новая проверка `merchant_cache_dead` отработала).
- Контур: pytest + ruff + `contract_delta` + `ratchet` + `cc_ratchet` + `build_css`; канон — `spec/PIPELINE.md`,
  `spec/TESTING.md`, `spec/ARCHITECTURE.md`; словарь терминов — `CONTEXT.md`.
- Дизайн: ребрендинг v2 «Стикербук» — направление принято (`DESIGN_DIRECTION_V2_2026-09-29.md`); Wave 0/1
  закоммичены; 3D-графики отклонены (искажают значения).

## Что активно / в работе (срез)
- **Wave13 (AgentRouter-ревью): адъюдикация закрыта 15–16.10** (сводки `ADJUDICATION_WAVE13_SUMMARY_2026-10-16.md`,
  `ADJUDICATION_WAVE13_SUMMARY_FB_2026-10-16.md`). **C1/C2/C3 csv_import — реализованы 16.10** (TDD, `a7e9cad`).
  **Решения-независимый срез волны A (②+④) — реализован 16.10 ночь-2** (TDD, закоммичен `9403d45`; см. «Последние сессии»).
  **19.10: пакет `spend_wavea` закоммичен (`dc6bcf3`), сервисы перезапущены (см. «Последние сессии»).**
  **Ждут решений владельца:** матчер (границы слова), ЕРИП-контракт, egress-redaction (или снятие), форма пиннинга
  установщика, approve-бейдж, минимизация doctor print. Окно 02:00 UTC 17.10 доберёт `bootgate`/`bootgen13`/
  `bootfixes` (fb-полоса, стриминг SSE).
- **21.10 (privacy pack — по решению владельца):** (1) `doctor` по умолчанию **не печатает** тексты
  операций/мерчантов в `detail` — только коды и счётчики, полный текст по `doctor --details`
  (`run_checks(details=...)`, CLI `--details`; библиотечный default остался `True` → старые тесты целы);
  (2) **egress-redaction** перед LLM: новый `redact.py` маскирует карты/счета, телефоны, e-mail в
  `description`/`merchant` и в few-shot; суммы и текст мерчанта не трогаются; opt-out
  `SPENDTRACK_LLM_REDACT=0`; вызов из единственного шлюза `prompts.py`. Тесты: +17
  (`test_doctor_privacy.py`, `test_llm_redaction.py`), full-suite **1088 passed**, ruff чисто,
  ratchet/cc — ok. **Не закоммичено** (по команде владельца); `contract_delta` — **snapshot сделан**
  (21.10, `/careful`), `check` = ok; `app.css.inputs.json` пересобран (`build_css`) — дрейф с origin снят.
  Ревью телефона (21.10 09:29) учтено: API `/health/data` тоже `details=False` (+тест), `--json`
  минимизирован (+тест), hint только при скрытых данных, `merchant_cache_dead` в `--details` —
  `key:<sha1[:8]>` (не сырой текст), обрезка merchant в few-shot возвращена к ровным 20 символам,
  тесты redact: IBAN, +375, ложные срабатывания, идемпотентность.
- **Открытые решения владельца (после privacy pack):** матчер (границы слова), ЕРИП-контракт,
  форма пиннинга установщика, approve-бейдж. Goals Ф3 (LLM-советы) — после egress-redaction (теперь есть).
- **Bootstrap-контур:** волны ⑤⑥ закрыты 16.10 вечером — `bootscripts_tail_test.py` 12/12
  (K1-герметичность: копия cmd без абсолютного фолбэка; SEEN; N4) и `agentrouter_probe_test.py` 6/6
  (E/F наблюдают журнал фейка, fail-closed); popups v3 (C1/N1/S1/S5/S2) + тест 27/27; habr-C2-матчер 26/26.
  bootstrap закоммичен и запушен (`a8bfd4c`, `f63e9ce`). Остаток ⑦ (дизайн): изоляция зелёной ветки
  генераторов (Н1), S-пункты `test_make_wave578_parts.py`, O1 `popups.cmd`.
- **Прочие открытые:** B-14 (session_v2 миграция), B-22/B-27 (bootstrap-скрипты), fb_c-остаток;
  PR #6 (setup-uv) — open, решение владельца; push: spend — ahead 1 (`9403d45`, по команде), bootstrap — чисто.
  B-19 (spend_misc C1) — **закрыт 14.10** (`5975660`, сужение Codespaces-Origin до своего пространства).
- **Очередь применения (процессное):** `RECOMMENDATIONS_APPLY_QUEUE_2026-09-24.md` §F; канонизация
  continue.md — выполнена 16.10 (этот файл).

## Последние сессии (сжато)
- **16.10 (ночь-2, волна A — решения-независимый пакет):** TDD red→green по адъюдикациям wave13 (C1/C2/Н-2/Н-6/Н-7,
  HELP1 #1/#2/#4, S7): `LLM_ENV_VARS`=7 (единый источник; тесты/доки опираются на него), PRIVACY «Как выключить»
  + free-матрица (README синхрон), `_EXAMPLES_LIMIT=8`, numbers-sync 300/80/8; anonymize-стемы русских шапок
  (описание/карта/документ/ФИО); `confirm` — rc=2 вне таксономии (до Store); htmx-дубликат — «Не добавлено»+OOB;
  seed кэша по `merchant or description`; doctor live-set с описаниями merchantless. Гейты: pytest **1061**,
  ruff/contract (snapshot `+LLM_ENV_VARS`)/ratchet/cc/build_css — ok; мутации 8/8 (+доктор-перепроверка). Живые факты —
  `%TEMP%\opencode\wave_a_live\report.txt` (confirm rc2/rc0; seed 3 путей; doctor ok; анонимайзер без PII;
  temp-стенд 8767: dup+бейдж, погашен). Закоммичено `9403d45` (по команде; трейлер `Contract-Change:`); push — по команде.
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
