"""Периметр браузера: гейт Origin/Sec-Fetch-Site для state-changing запросов.

Модель угроз: приложение слушает loopback без аутентификации, поэтому любая открытая в браузере
страница может отправить POST на `127.0.0.1:8766` (simple request без префлайта) и изменить данные.
Гейт закрывает кросс-сайтовые мутации, не ломая CLI/тесты/обычные формы:

* `Origin` есть → hostname обязан быть loopback-именем (порт любой: тесты и кастомные порты);
* `Origin` нет, но есть `Sec-Fetch-Site` → только `same-origin`/`none`;
* нет ни того, ни другого → пропускаем: это не браузер (curl/CLI/TestClient), а веб-страница
  не может «снять» Origin — модель угроз не страдает (OWASP CSRF Cheat Sheet: fallback-проверка).

CSRF-токены не нужны: нет сессии/cookie, токен не к чему привязывать. `HX-Request` — не гейт
(сломал бы форму без JS), допустим как дополнительный сигнал.
"""
from __future__ import annotations

import hmac
import os
import time
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost"})  # IPv6-loopback не поддерживаем:
# сервер слушает 127.0.0.1, а Starlette TrustedHost не разбирает `[::1]` (split по ':').
ALLOWED_SCHEMES = frozenset({"http", "https"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_FETCH_SITES = frozenset({"same-origin", "none"})
DEFAULT_CODESPACES_DOMAIN = "app.github.dev"
_TRUSTED_HOSTS_ENV = "SPENDTRACK_TRUSTED_HOSTS"


def codespaces_enabled() -> bool:
    """GitHub Codespaces: прокси форвардинга сохраняет публичный Host (см. README/Codespaces)."""
    return os.environ.get("CODESPACES", "").strip().lower() in {"true", "1"}


def codespaces_domain() -> str:
    """Домен форвардинга портов Codespaces (env GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN)."""
    return (os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "").strip().lower()
            or DEFAULT_CODESPACES_DOMAIN)


def _in_codespaces_domain(host: str) -> bool:
    domain = codespaces_domain()
    return host == domain or host.endswith("." + domain)


def _codespace_namespace(host: str) -> str | None:
    """Пространство (кодовое имя) Codespace для `host = <name>-<port>.<домен>`.

    None — хост вне домена форвардинга или без ожидаемой формы `<name>-<port>`.
    B-19 (spend_misc C1): доверие Codespaces сужено до СВОЕГО пространства — чужой codespace
    с тем же доменом `app.github.dev` больше не проходит.
    """
    domain = codespaces_domain()
    suffix = "." + domain
    if not host.endswith(suffix):
        return None
    label = host[: -len(suffix)]
    name, sep, _port = label.rpartition("-")
    return name if sep and name else None


def _is_loopback_host(host: str | None) -> bool:
    """True для loopback bind; `0.0.0.0`/LAN — нет (нужен HTTPS/явный opt-in)."""
    return (host or "").strip().lower() in {"127.0.0.1", "localhost", "::1"}


def _is_trusted_proxy_host(host: str | None) -> bool:
    """True только для явно разрешённого `SPENDTRACK_TRUSTED_HOSTS` (не loopback/testserver)."""
    hostname = (host or "").strip().lower().split(":", 1)[0]
    return bool(hostname) and hostname in set(_extra_trusted_hosts())


def _remote_path_allowed(path: str, method: str) -> bool:
    """Удалённый (proxy/Tailscale) доступ — только к capture-странице и POST транзакции.

    Главный UI (`/`, `/approve`, `/settings`, API чтения) через trusted host не отдаём:
    даже при ошибке в ACL/прокси это не должно раскрывать финансовые данные.
    """
    if path == "/capture" and method == "GET":
        return True
    if path.startswith("/static/") and method in {"GET", "HEAD"}:
        return True
    return path == "/api/transactions" and method == "POST"


_CAPTURE_RATE_WINDOW_SECONDS = 60.0
_CAPTURE_RATE_LIMIT = 10
_capture_rate_buckets: dict[str, list[float]] = {}
_CAPTURE_TOKEN_ENV = "SPENDTRACK_CAPTURE_TOKEN"
# Same-process marker set only by CaptureOnlyApp (capture_gateway.py); not a
# header, so a network client cannot spoof it.
_CAPTURE_EDGE_MARKER = "spendtrack.capture_edge_verified"


def _capture_token_ok(headers: Headers) -> bool:
    """App-token для remote POST: fail-closed, constant-time; токен не логируем."""
    expected = os.environ.get(_CAPTURE_TOKEN_ENV, "").strip()
    if not expected:
        return False
    supplied = headers.get("x-spendtrack-token", "")
    try:
        return hmac.compare_digest(supplied, expected)
    except TypeError:
        # Header bytes are decoded as Latin-1; non-ASCII str is unsupported by
        # compare_digest. Treat it as a wrong token, not an unhandled 500.
        return False


def _capture_rate_ok(client: str, now: float | None = None) -> bool:
    """Простой in-memory лимит 10 POST/мин на клиента (только remote capture)."""
    current = time.monotonic() if now is None else now
    bucket = _capture_rate_buckets.setdefault(client or "unknown", [])
    cutoff = current - _CAPTURE_RATE_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _CAPTURE_RATE_LIMIT:
        return False
    bucket.append(current)
    return True


def _reset_capture_rate() -> None:
    """Только для тестов/диагностики; не публичный API."""
    _capture_rate_buckets.clear()


class _RemoteAccessGuard:
    """ASGI-гард для запросов через trusted HTTPS-прокси/Tailscale.

    Path isolation + rate limit + app-token; Tailscale ACL — дополнительный сетевой слой.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        state = scope.get("state") or {}
        if state.get(_CAPTURE_EDGE_MARKER) is True:
            # CaptureOnlyApp already enforced path isolation + token + rate limit.
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        if _is_trusted_proxy_host(headers.get("host")):
            path = scope.get("path", "")
            method = scope.get("method", "GET")
            if not _remote_path_allowed(path, method):
                response = JSONResponse({"detail": "remote path blocked"}, status_code=403)
                return await response(scope, receive, send)
            if path == "/api/transactions" and method == "POST":
                if not _capture_token_ok(headers):
                    response = JSONResponse({"detail": "capture token required"}, status_code=401)
                    return await response(scope, receive, send)
                client = (scope.get("client") or ("unknown", 0))[0]
                if not _capture_rate_ok(client):
                    response = JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
                    return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def _extra_trusted_hosts() -> list[str]:
    """Явные host-имена из env (HTTPS reverse proxy/Tailscale Serve), только по одному списку.

    Не использовать для LAN HTTP: TLS-терминация и аутентификация — на прокси/оверлее.
    Формат: `SPENDTRACK_TRUSTED_HOSTS=spend.tailnet.ts.net,spend.example` (без схемы/порта).
    """
    raw = os.environ.get(_TRUSTED_HOSTS_ENV, "")
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def trusted_hosts() -> list[str]:
    """Host-имена для TrustedHostMiddleware: loopback + testserver (+ Codespaces, env proxy).

    `SPENDTRACK_TRUSTED_HOSTS` — явный opt-in для HTTPS reverse proxy/Tailscale Serve;
    дефолт остаётся loopback-only, поэтому случайный `--host 0.0.0.0` не открывает UI по LAN.
    """
    hosts = sorted(set(sorted(ALLOWED_HOSTNAMES) + ["testserver"] + _extra_trusted_hosts()))
    if codespaces_enabled():
        hosts.append(f"*.{codespaces_domain()}")
    return hosts


def frame_ancestors() -> str:
    """CSP frame-ancestors: локально 'none'; в Codespaces — Simple Browser редактора (домен GitHub)."""
    if codespaces_enabled():
        return f"'self' https://*.{codespaces_domain()}"
    return "'none'"


def content_security_policy() -> str:
    """CSP приложения (script-src строго 'self' — см. SECURITY.md)."""
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; "
        f"frame-ancestors {frame_ancestors()}; form-action 'self'"
    )


def origin_allowed(origin: str | None, sec_fetch_site: str | None,
                   request_host: str | None = None) -> bool:
    """True — state-changing запрос можно пропустить (проверка выполнена успешно или неприменима).

    Аудит 24.09: при известном `request_host` Origin обязан совпадать с фактическим адресом
    сервера (netloc) — иначе любое другое локальное приложение могло слать POST на 8766.
    """
    if origin:
        parts = urlsplit(origin)
        if parts.scheme.lower() not in ALLOWED_SCHEMES:
            return False  # "null"/javascript:/data: и прочий мусор
        if request_host:
            rq = request_host.strip().lower()
            if (parts.netloc or "").lower() == rq:
                return True
            host = (parts.hostname or "").lower()
            if not codespaces_enabled():
                return False
            # B-19 (spend_misc C1): Codespaces-доверие — только СВОЁ пространство
            # (`<codespace>-<port>`): Origin и request_host обязаны быть одним codespace.
            rq_host = rq.rsplit(":", 1)[0]
            ns_origin = _codespace_namespace(host)
            ns_request = _codespace_namespace(rq_host)
            return ns_origin is not None and ns_origin == ns_request
        host = (parts.hostname or "").lower()
        if host in ALLOWED_HOSTNAMES:
            return True
        # Codespaces без request_host (legacy-путь: TestClient/прямые вызовы) — домен как раньше;
        # middleware main.py всегда передаёт request_host, там действует сужение B-19 выше.
        return codespaces_enabled() and _in_codespaces_domain(host)
    if sec_fetch_site:
        return sec_fetch_site.strip().lower() in SAFE_FETCH_SITES
    return True
