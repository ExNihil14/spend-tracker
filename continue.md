# Continue.md — состояние проекта Spendtrack

Активный срез (обновлён 12.11.2026). Посессионная история — приватный архив
`D:\dev\docs\machine\spendtrack\SESSION_HISTORY.md` (переносы 24.09, 16.10, 12.11).
Бюджет: ≤150 строк; гейт `agent_context_audit.py`. Новое — в «Сейчас»; закрытые этапы
уезжают в архив, а не копятся здесь.

## Сейчас (12.11.2026)
- **Git:** HEAD `a48935e` `feat(capture): add capture-only remote edge` (12 files, +560/−35),
  `origin/main = cfd8963`, **ahead 1**; worktree: `AGENTS.md` + `continue.md` modified
  (instruction review 12.11, uncommitted), остальные файлы не тронуты. Push — только по явной команде owner.
- **Capture edge (прод):** отдельный `spendtrack capture-serve` на `127.0.0.1:8767` с
  `CaptureOnlyApp`: path/token решаются независимо от `Host`; `/`, `/approve`, `/settings`
  закрыты на edge; каждый POST требует `SPENDTRACK_CAPTURE_TOKEN`. Запуск — user Startup
  `spendtrack-capture-8767.vbs` + 5-мин watchdog (PID 17000), listener PID 11980, логи
  `data/capture/`, БД `data/spend.db`, токен из `C:\Users\HP\.spendtrack\capture-token.txt`
  (значение не печатать). Main UI `8766` — только loopback, в Serve не указывается.
- **Serve:** `443 -> http://127.0.0.1:8767`; Funnel off. Tailnet 1 user/1 device, ACL пока
  default allow-all — сузить до `:443` до подключения второго устройства (evidence:
  `D:\dev\docs\machine\agentrouter_review\2026-11-09-capture-security\ACL_CHECK_2026-11-11.md`).
- **Live gate 12.11 PASS:** local/public non-ASCII token **401**; `/capture` **200**;
  `/` и `/static/../approve` **403**; tokenless POST **401**; valid token + `{}` **422**.
  UI smoke 11.11 (390×844 через Serve): `/capture` 200, остальные пути 403, ошибок assets/CSP/JS
  нет; токен не вводился, POST не отправлялся. Evidence:
  `D:\dev\docs\machine\agentrouter_review\2026-11-11-capture-edge\LIVE_GATE_2026-11-12.md`,
  `...\2026-11-09-capture-security\LIVE_UI_SMOKE_2026-11-11.md`.
- **Гейты:** pytest **1312 passed, 1 skipped, 102 deselected**; edge **20 passed**; ruff,
  `contract_delta check`, `agent_context_audit` — OK.
- **Ревью:** free `arch-reviewer` — новых P0/P1 нет, `ACCEPTABLE-WITH-NOTES`; `SEC-01`
  (non-ASCII token → 401, не 500) и F10 (non-UTF-8 token-file → fail-closed rc=2) закрыты TDD.
  AgentRouter Sol stopped: C1 32K/24K → `429 rate_limit_exceeded` (eastus2), это TPM, не баланс;
  новых POST без нового gate нет. Evidence:
  `D:\dev\docs\machine\agentrouter_review\2026-11-11-capture-edge\RESULT_2026-11-11.md`.
- **Bootstrap:** `start-capture-8767.ps1` (foreign-port → rc=2, missing token → rc=1 с логом),
  `capture-watchdog.ps1` (`$LASTEXITCODE` → `watchdog.log`), `install-capture-startup.ps1`
  (WMI-запуск) — оффлайн-тест `capture_autostart_test.py` **10/10 PASS**; в git не закоммичены.

## Следующие шаги (по приоритету)
1. **Push** `spend-tracker` (`main` ahead 1) — отдельная команда owner; после push проверить
   remote CI (`lint-and-test`, `docker-smoke`; исторический фикс msgpack/Dockerfile — `6519632`).
2. **Телефонный пилот** (owner): `https://<tailnet-host>/capture` (хост — в приватном runbook),
   токен из защищённого файла; проверить добавление траты и `spendtrack count`. Runbook:
   `D:\dev\docs\machine\PWA_CAPTURE_OWNER_RUNBOOK_2026-11-01.md`.
3. **Owner-only ACL** в Tailscale Admin: разрешить только `:443` (сейчас allow-all; 1 user/1 device).
4. **Bootstrap commit** capture-скриптов + теста — по отдельной команде owner.
5. Опционально (нужен elevation): boot-before-logon task/NSSM для edge; чистка legacy capture-env
   в основном NSSM-сервисе.

## Блокеры / owner-gated
- Push, пилот, ACL — только owner.
- Boot-service и NSSM cleanup — elevation; OS-lane (BitLocker, ESU/0patch, BIOS F.41, uTorrent) —
  отдельные owner-решения.
- Legacy junction `D:\Android_SDK\Sdk` — удаление только после подтверждения и `cmd /c rmdir`.
- AgentRouter: без нового gate/cooldown не отправлять; проверить TPM-лимит токена.

## Backlog (не в текущем deliverable)
- Advisor deferred: D-22..D-30, D-32–D-34 (triage) — `spec/PHASE_C_ADVISOR.md`.
- Remote CI после push; PR #6 (setup-uv) — решение owner.

## Известные ограничения/грабли
- Правка юзера → merchant_cache + few-shot (правит будущий импорт).
- Не запускать qwen 7b одновременно с dev-сервером (GTX 1050 4GB).
- «Готово» без фактической проверки не принимается: diff/запуск/UI — факт, а не отчёт.
- Демо-стенд 8799 — только с `SPENDTRACK_DB_PATH=data/demo.db` (иначе молча прод-БД;
  см. скилл verify-spendtrack).
- Инженерные грабли/уроки — `spec/PIPELINE.md`, `spec/TESTING.md`, `spec/ARCHITECTURE.md`.

## Канон (не дублируем)
- Ключевые решения — `AGENTS.md` §«Ключевые решения» + `spec/ARCHITECTURE.md`.
- Git-процесс — `AGENTS.md` §«Git-процесс»; commit/push только по команде owner.

## Возврат к работе
- Порядок: `AGENTS.md` → `D:\dev\docs\machine\AGENT_ENVIRONMENT_PLAN.md` (статус) → этот файл →
  `CONTEXT.md` → `spec/` по задаче. Handoff — если сессия длинная или контекст > ~150K.
