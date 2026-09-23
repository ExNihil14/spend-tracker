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

import os
from urllib.parse import urlsplit

ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost"})  # IPv6-loopback не поддерживаем:
# сервер слушает 127.0.0.1, а Starlette TrustedHost не разбирает `[::1]` (split по ':').
ALLOWED_SCHEMES = frozenset({"http", "https"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_FETCH_SITES = frozenset({"same-origin", "none"})
DEFAULT_CODESPACES_DOMAIN = "app.github.dev"


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


def trusted_hosts() -> list[str]:
    """Host-имена для TrustedHostMiddleware: loopback + testserver (+ домен Codespaces).

    Прокси Codespaces СОХРАНЯЕТ Host (`<codespace>-<port>.app.github.dev`), поэтому без этого
    демо-URL отдавал бы 400. Домен контролируется GitHub — DNS-rebinding не расширяется
    (чужой сайт не может обслуживаться на поддомене app.github.dev).
    """
    hosts = sorted(ALLOWED_HOSTNAMES) + ["testserver"]
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


def origin_allowed(origin: str | None, sec_fetch_site: str | None) -> bool:
    """True — state-changing запрос можно пропустить (проверка выполнена успешно или неприменима)."""
    if origin:
        parts = urlsplit(origin)
        if parts.scheme.lower() not in ALLOWED_SCHEMES:
            return False  # "null"/javascript:/data: и прочий мусор
        host = (parts.hostname or "").lower()
        if host in ALLOWED_HOSTNAMES:
            return True
        # Codespaces: прокси обычно переписывает Origin на localhost, но не полагаемся на это.
        return codespaces_enabled() and _in_codespaces_domain(host)
    if sec_fetch_site:
        return sec_fetch_site.strip().lower() in SAFE_FETCH_SITES
    return True
