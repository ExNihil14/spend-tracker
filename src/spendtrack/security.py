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

from urllib.parse import urlsplit

ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost"})  # IPv6-loopback не поддерживаем:
# сервер слушает 127.0.0.1, а Starlette TrustedHost не разбирает `[::1]` (split по ':').
ALLOWED_SCHEMES = frozenset({"http", "https"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_FETCH_SITES = frozenset({"same-origin", "none"})


def origin_allowed(origin: str | None, sec_fetch_site: str | None) -> bool:
    """True — state-changing запрос можно пропустить (проверка выполнена успешно или неприменима)."""
    if origin:
        parts = urlsplit(origin)
        if parts.scheme.lower() not in ALLOWED_SCHEMES:
            return False  # "null"/javascript:/data: и прочий мусор
        return (parts.hostname or "").lower() in ALLOWED_HOSTNAMES
    if sec_fetch_site:
        return sec_fetch_site.strip().lower() in SAFE_FETCH_SITES
    return True
