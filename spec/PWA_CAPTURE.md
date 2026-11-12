# SPEC: mobile quick-capture (`/capture`)

Статус: **capture-only edge развёрнут как user-level Startup + watchdog (8767); Tailscale Serve
включён для remote-пилота; CAP-01 live gate PASS 11.11.2026; прод 8766 не перезапускался**.
Это mobile web first, **не** installable PWA (нет manifest/service worker/offline queue).

## Scope

- Один экран `/capture`: дата, сумма, описание → существующий `POST /api/transactions`.
- Используется телефоном через loopback или HTTPS reverse proxy (Tailscale Serve/Caddy).
- Без offline queue, service worker, camera, push, multi-user, облачной БД.
- `client_id` — optional UUID в API; страница `/capture` **всегда** отправляет hidden UUID
  (генерируется на загрузке, сохраняется для retry, ротируется после 200/409).

## Contract

`GET /capture` → HTML (тот же `static/capture.html`, один экран).

`POST /api/transactions` (JSON или form): `date`, `description`, `amount`, optional
`account`, `currency`, `client_id` (≤128). API `client_id` optional; `/capture` всегда
отправляет hidden UUID. Ответ — как у существующего API; `HX-Request` → HTML-фрагмент.

`client_id` reservation хранится в `capture_idempotency(client_id PK, tx_id)`:
- same `client_id` + тот же payload (date/amount/description/account/currency после
  нормализации) → **replay**: 200, htmx «Уже добавлено», тот же `tx_id`, второй строки нет;
- same `client_id` + другой payload → htmx «Не добавлено», JSON **409**;
- reservation + transaction + UPDATE в одной транзакции (`BEGIN IMMEDIATE`), rollback
  при исключении, DELETE при `tx_id is None`; повторный запрос не получает вечный 409.
- race двух запросов: один создаёт строку, второй — replay/409/503; `BEGIN IMMEDIATE` busy
  возвращает **503**, клиент повторяет **с тем же** `client_id` (после commit первого — replay
  200, без второй строки).

## Security

- **Сетевой периметр — отдельный процесс `spendtrack capture-serve`** (по умолчанию
  `127.0.0.1:8767`), а не главный UI 8766. `CaptureOnlyApp` решает по пути и методу, **не по
  `Host`**: `GET/HEAD /capture`, `GET/HEAD /static/*`, `POST /api/transactions`; всё остальное
  (`/`, `/approve`, `/settings`, GET API) → **403**. Спуф `Host: 127.0.0.1` не меняет решение.
- В текущем деплое процесс поднимается из user Startup через `capture-watchdog.ps1`
  (проверка каждые 5 минут, без admin). Task/NSSM-вариант — только с elevation; task-скрипт
  `register-capture-task.ps1` оставлен для этого. Токен читается CLI из файла
  `--token-file` и не попадает в action/командную строку/лог.
- Главный `spendtrack serve` остаётся loopback-only. `tailscale serve` направляется **только**
  на capture-порт 8767; 8766 в Serve не указывается. `SPENDTRACK_TRUSTED_HOSTS` нужен
  публичному Host для `TrustedHostMiddleware`; это не граница path isolation.
- **Path isolation:** `CaptureOnlyApp` разрешает `GET/HEAD /capture`, `GET/HEAD /static/*`,
  `POST /api/transactions`; статические пути с dot-сегментами (`..`, `.`), backslash или NUL
  после percent-decoding отклоняются на edge (defense-in-depth против path-normalization).
- `POST /api/transactions` на capture-edge требует app-token `SPENDTRACK_CAPTURE_TOKEN`
  (header `X-Spendtrack-Token`, constant-time) на **каждом** запросе; missing/wrong → **401**.
  Tailscale ACL — дополнительный слой.
- `capture-serve` fail-closed: без env `SPENDTRACK_CAPTURE_TOKEN` и без непустого `--token-file`
  не стартует (rc=2). Host фиксирован loopback, опции LAN нет.
- Origin/Sec-Fetch-Site guard (existing) — same-origin proxy Host проверен unit-тестом.
  Edge не доверяет `Host` и не переписывает `Origin`.
- Rate limit: 10 POST/мин на клиента на capture-edge (in-memory, per-process). За proxy
  backend видит 127.0.0.1 → bucket общий; для single owner принято. Edge и app-guard не
  списывают лимит дважды (same-process scope marker, недоступный по сети).
- `Cache-Control: no-store` для API/HTML (existing middleware); static — no-cache.
- `spendtrack serve --host` не-loopback без `SPENDTRACK_ALLOW_INSECURE_LAN=1` → отказ (rc=2).
- Token хранится в sessionStorage; `client_id` — localStorage (для retry). CSP —
  `script-src 'self'`, сторонних скриптов нет; описания экранируются (XSS-regression
  `test_ui_polish`). sessionStorage остаётся same-origin поверхностью: компрометация
  скрипта приложения равна компрометации сессии, принято для single-owner.
- **Tailscale ACL:** grant owner user/device → laptop:443 (Serve), backend capture-порт
  `127.0.0.1:8767` в tailnet не публикуется; никаких tagged/foreign identities.
  `tailscale status` — 1 user / 1 device; Serve tailnet-only. Проверка 11.11:
  `tailscale debug netmap` показывает **default allow-all tailnet**, не owner-only; пока
  устройство одно, это фактически owner-only, но ACL нужно сузить до `:443`. Evidence:
  `ACL_CHECK_2026-11-11.md`; app-token обязателен.

## Deployment (B)

1. Tailscale на ноутбуке и телефоне; ACL owner-only. Funnel не используем.
2. Главный UI: `spendtrack serve` → `127.0.0.1:8766` (не в Serve). Capture-edge:
   `spendtrack capture-serve --port 8767 --token-file C:\Users\HP\.spendtrack\capture-token.txt`
   с `SPENDTRACK_TRUSTED_HOSTS=<machine>.tailnet.ts.net`; отдельные
   `SPENDTRACK_DATA_DIR=...\data\capture` и `SPENDTRACK_DB_PATH=...\data\spend.db`.
   Для текущего пользователя установка без admin:
   `powershell -File D:\dev\bootstrap\bin\install-capture-startup.ps1`
   (Startup + 5-минутный watchdog). С admin — `register-capture-task.ps1`/NSSM.
3. `tailscale serve --bg --yes 8767` → HTTPS → `127.0.0.1:8767`. **Никогда** не `... 8766`.
4. Открыть `https://<machine>.tailnet.ts.net/capture`.
5. Проверить нормальный Host и спуф `Host: 127.0.0.1`: `/`, `/approve`, `/settings` должны
   быть 403, tokenless POST — 401; при провале сразу `tailscale serve reset`.
   Текущий пилот: Serve включён на 8767; токен на телефон ещё не переносился.
   Пошаговый owner runbook: `D:\dev\docs\machine\PWA_CAPTURE_OWNER_RUNBOOK_2026-11-01.md`
   (обновлён 11.11; старые инструкции `Serve → 8766` удалены).

## Coverage (current)

| Area | Tests |
|---|---|
| Page/fields/hidden client_id | `tests/test_capture.py` (9) |
| Browser e2e: hidden client_id submit | `tests/e2e/test_capture_e2e.py` (1) |
| Capture-only edge: Host spoof, path, token, rate | `tests/test_capture_gateway.py` (20) |
| Path isolation/rate/token (legacy guard) | `tests/test_remote_access.py` (3) |
| Trusted hosts/Codespaces/Origin | `tests/test_security_perimeter.py` (16) |
| CLI LAN guard + capture-serve | `tests/test_cli_serve.py` (11) |
| Phase C contract v1 | `tests/test_advisor_contract.py` (5) |

Full suite: **1312 passed, 1 skipped**, ruff clean. Browser e2e: **1 passed** (`tests/e2e/test_capture_e2e.py`, temp server; CI job `e2e` installs chromium and runs `pytest -m e2e`; without browser local run skips, in CI it fails).
Branch coverage (targeted `test_api` + capture/security/CLI): `routers/api.py` **79%**,
`security.py` **96%**, `/capture` route covered; module-wide `routers/frontend.py` 51% due
unrelated pages, **capture path itself covered**.

## Known gaps / not covered

- CAP-01 live gate **пройден 11.11.2026** на `capture-serve` 8767: normal и spoofed
  `Host: 127.0.0.1` дали `/`, `/approve`, `/settings` 403; tokenless POST 401; valid token +
  empty body 422. Первый gate завершился reset; затем persistent Startup/watchdog развернут,
  Serve снова включён на 8767 для пилота, re-gate те же статусы. Post-hardening re-gate 22:45:
  `capture-serve` перезапущен (main 8766 не тронут), local/public `/capture` **200**, `/` **403**,
  `/static/../approve` через `curl --path-as-is` **403**; full suite **1312 passed**. Evidence:
  `LIVE_GATE_2026-11-11.md`, `LIVE_UI_SMOKE_2026-11-11.md`, `DEPLOY_2026-11-11.md`.
- SEC-01/F10 live re-gate **12.11.2026 PASS**: capture-edge перезапущен (main 8766 не тронут);
  local/public non-ASCII token **401** (не 500), `/capture` **200**, `/` и
  `/static/../approve` **403**, tokenless POST **401**, valid token + `{}` **422**; temp
  non-UTF-8 token file не поднял listener (fail-closed). Evidence:
  `LIVE_GATE_2026-11-12.md`.
- **Главный UI 8766 нельзя указывать в Serve:** app-level guard один не отличает прокси-запрос
  со спуфленным `Host: 127.0.0.1` от локального. Граница — только отдельный capture-edge +
  операционное правило «Serve → 8767».
- Текущий деплой — **user Startup + `capture-watchdog.ps1`** (проверка 5 минут): работает после
  logon, без admin. Task/NSSM-регистрация требует elevation, поэтому `register-capture-task.ps1`
  не установлен; его можно запустить позже из elevated shell. Boot-service (до logon) не настроен.
- В env основного NSSM-сервиса 8766 остаются legacy `SPENDTRACK_CAPTURE_TOKEN` и
  `SPENDTRACK_TRUSTED_HOSTS`; capture-edge берёт токен из файла. Удаление legacy-копии требует
  elevated NSSM и restart; до пилота это не блокер, но токен-гигиена — отдельное решение owner.
- Remote browser smoke 11.11.2026 (390×844, public Serve URL): `/capture` **200**; `/`, `/approve`,
  `/settings`, `/health`, GET `/api/transactions` → **403**; no missing assets/CSP/JS errors on
  load; token field not filled and no POST sent. Evidence: `LIVE_UI_SMOKE_2026-11-11.md`.
  Footer `На главную` is hidden on non-loopback hosts (the main UI is not remotely exposed);
  local `/capture` keeps it.
- Actual phone/browser install, iOS Safari quirks, service worker/offline — out of scope.
- `capture_idempotency` race under real concurrent load only unit-tested (503→replay 200).
- Contract baseline check: **ok** (`scripts/contract_delta.py check`); capture-edge names are
  internal/private, so no baseline snapshot was needed. Any future public contract change still
  requires owner `/careful` + snapshot in the same commit.
- Rate limit is per-process, not shared across workers; current single-process edge.

## DoD

- [x] one-screen page, accessible labels/focus/min 44px targets.
- [x] reuse POST, no new financial read API, no-store.
- [x] remote path isolation + app token + rate limit.
- [x] strict client_id: same-payload replay, different-payload 409, failure rollback.
- [x] unit/integration tests, full suite green.
- [x] backup + restore drill (`spendtrack backup --drill`) перед remote-пилотом
  (09.11 22:25, `restore-drill: ok`).
- [x] Tailscale/ACL + live CSRF smoke, включая попытку `Host: 127.0.0.1` через Serve —
  **PASS 11.11.2026** (initial reset; persistent re-gate PASS). Evidence: `LIVE_GATE_2026-11-11.md`.
- [ ] owner-only ACL console check (tailnet 1 user/1 device; Serve tailnet-only; app gate passed).
- [x] persistent `capture-serve` deployment — user Startup + 5-min watchdog (8767); admin task/NSSM
  optional. Phone token entry/pilot remains owner action.
- [x] contract baseline check — **ok**; public contract unchanged (edge internals private).
- [ ] owner review/push (Serve is live for pilot; 8766 never a Serve target).

## Non-goals

Offline queue, service worker/manifest, camera/receipt scan, push, multi-user, CRDT,
cloud DB, Phase C re-review.
