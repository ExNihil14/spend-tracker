# SPEC: mobile quick-capture (`/capture`)

Статус: **реализовано локально, не задеплоено; live 8766 не перезапускался**. Это
mobile web first, **не** installable PWA (нет manifest/service worker/offline queue).

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
- same `client_id` + любой payload → htmx «Не добавлено», JSON **409**;
- reservation + transaction + UPDATE в одной транзакции (`BEGIN IMMEDIATE`), rollback
  при исключении, DELETE при `tx_id is None`; повторный запрос не получает вечный 409.
- race двух запросов: один создаёт строку, второй — 409/503; `BEGIN IMMEDIATE` busy
  возвращает **503**, клиент повторяет **с тем же** `client_id` (retry → 409, без второй строки).

### Phase C import boundary

Интеграция (PWA/CLI) импортирует только `spendtrack.advisor.contract` (`AdvisorProtocol`,
`TemplateAdvisor`, `run_advisor_flow`, `PHASE_C_CONTRACT_VERSION`). Прямые импорты
`advisor.facts`/`slots`/`llm` — вне контракта; breaking change = bump version + adapter.

## Security

- Remote Host разрешается только явным `SPENDTRACK_TRUSTED_HOSTS` (HTTPS proxy/Tailscale).
- Path isolation: remote `/capture` и `/static/*` — GET; `POST /api/transactions`; остальное
  (`/`, `/approve`, `/settings`, GET API) → **403**.
- `POST` remote требует app-token `SPENDTRACK_CAPTURE_TOKEN` (header `X-Spendtrack-Token`,
  constant-time); missing/wrong → **401**. Tailscale ACL — дополнительный слой.
- Origin/Sec-Fetch-Site guard (existing) — same-origin proxy Host проверен unit-тестом.
- Rate limit: 10 POST/мин на клиента для remote capture (in-memory, per-process). За proxy
  backend видит 127.0.0.1 → bucket общий; для single owner принято.
- `Cache-Control: no-store` для API/HTML (existing middleware); static — no-cache.
- `spendtrack serve --host` не-loopback без `SPENDTRACK_ALLOW_INSECURE_LAN=1` → отказ (rc=2).
- Token хранится в sessionStorage; `client_id` — localStorage (для retry).
- **Tailscale ACL:** grant owner user/device → laptop:8766; никаких tagged/foreign identities.
  ACL вживую не проверялся (Tailscale не установлен); app-token обязателен.

## Deployment (B)

1. Tailscale на ноутбуке и телефоне; ACL owner-only. Funnel не используем.
2. `tailscale serve` → HTTPS → `127.0.0.1:8766`.
3. Перед запуском: `SPENDTRACK_TRUSTED_HOSTS=<machine>.tailnet.ts.net`,
   `SPENDTRACK_CAPTURE_TOKEN=<random>`; перезапуск — по owner go.
4. Открыть `https://<machine>.tailnet.ts.net/capture`.
5. Проверить, что proxy сохраняет публичный Host; иначе Origin-guard даст 403 на POST.

## Coverage (current)

| Area | Tests |
|---|---|
| Page/fields/hidden client_id | `tests/test_capture.py` (6) |
| Browser e2e: hidden client_id submit | `tests/e2e/test_capture_e2e.py` (1) |
| Path isolation/rate/token | `tests/test_remote_access.py` (3) |
| Trusted hosts/Codespaces/Origin | `tests/test_security_perimeter.py` (16) |
| CLI LAN guard | `tests/test_cli_serve.py` (8) |
| Phase C contract v1 | `tests/test_advisor_contract.py` (3) |

Full suite: **1277 passed**, ruff clean. Browser e2e: **1 passed** (`tests/e2e/test_capture_e2e.py`, temp server; CI job `e2e` runs `pytest -m e2e`).
Branch coverage (targeted `test_api` + capture/security/CLI): `routers/api.py` **79%**,
`security.py` **96%**, `/capture` route covered; module-wide `routers/frontend.py` 51% due
unrelated pages, not the capture path.

## Known gaps / not covered

- Real Tailscale Serve/ACL, live proxy Host/Origin, live CSRF — no Tailscale installed.
- Actual phone/browser install, iOS Safari quirks, service worker/offline — out of scope.
- `capture_idempotency` race under real concurrent load only unit-tested (503→retry 409).
- Contract baseline (`/capture`, `client_id`, `capture_idempotency`, contract v1) not snapshotted;
  `contract_delta.py snapshot` blocked by safety-gate until owner `/careful`.
- Rate limit is per-process, not shared across workers; current single-process service.

## DoD

- [x] one-screen page, accessible labels/focus/min 44px targets.
- [x] reuse POST, no new financial read API, no-store.
- [x] remote path isolation + app token + rate limit.
- [x] strict client_id + failure rollback.
- [x] unit/integration tests, full suite green.
- [ ] Tailscale/ACL + live CSRF smoke.
- [ ] contract baseline update (owner `/careful`).
- [ ] owner review/push/live restart.

## Non-goals

Offline queue, service worker/manifest, camera/receipt scan, push, multi-user, CRDT,
cloud DB, Phase C re-review.
