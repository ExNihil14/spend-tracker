from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from spendtrack.config import PKG_DIR, ensure_config_dir, load_settings, resolve_data_dir
from spendtrack.routers.api import router as api_router
from spendtrack.routers.frontend import router as frontend_router
from spendtrack.routers.settings import router as settings_router
from spendtrack.security import SAFE_METHODS, content_security_policy, origin_allowed, trusted_hosts

cfg = load_settings()
LOG_DIR = resolve_data_dir() / "logs"


_LOGGING_DONE = False  # идемпотентность: при импорте + main() не плодить handler'ы


def _setup_logging() -> None:
    """Файловые логи с ротацией (5MB × 3). Idempotent: настраивается один раз.

    Добавляет handler напрямую к uvicorn/loggers + spendtrack с propagate=False
    (иначе записи дублируются при log_config=None, а 2 RotatingFileHandler'а на
    один файл ломают ротацию на Windows: WinError 32).
    """
    global _LOGGING_DONE
    if _LOGGING_DONE:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / "spendtrack.log", maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "spendtrack"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING if name == "uvicorn.access" else logging.INFO)
        logger.propagate = False  # не пропагировать в root (двойная запись)
    _LOGGING_DONE = True


app = FastAPI(title="Spendtrack", version="0.1.0")
_setup_logging()
# DNS-rebinding/Host-атаки: loopback-имена (порт Starlette отбрасывает сам) + в Codespaces —
# домен форвардинга портов (прокси сохраняет публичный Host; см. spendtrack.security.trusted_hosts).
# "testserver" — Host по умолчанию у FastAPI TestClient (в тестах); публично не резолвится.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts())
app.include_router(frontend_router)
app.include_router(settings_router)
app.include_router(api_router, prefix="/api")

app.mount("/static", StaticFiles(directory=PKG_DIR / "static"), name="static")

# Минимальный CSP для локального приложения: ограничиваем источники/встраивание.
# script-src — строго 'self': inline-скрипты и hx-on::* вынесены в /static/app.js (см. base.html),
# htmx.config.allowEval=false. style-src 'unsafe-inline' остаётся: inline-стили цветов категорий и темы.
# Сборка строки — spendtrack.security.content_security_policy() (в Codespaces добавляется
# frame-ancestors для Simple Browser редактора).


@app.middleware("http")
async def _origin_guard(request, call_next):
    """Кросс-сайтовые state-changing запросы — 403 (см. spendtrack.security)."""
    if request.method not in SAFE_METHODS and not origin_allowed(
            request.headers.get("origin"), request.headers.get("sec-fetch-site")):
        return JSONResponse({"detail": "cross-origin request blocked"}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", content_security_policy())
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # Кэш: статика с версией (?v=) — immutable на год; без версии — revalidate;
    # HTML/API — no-store (данные чувствительные; htmx-история у нас отключена: historyCacheSize=0).
    if request.url.path.startswith("/static/"):
        if request.query_params.get("v"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        else:
            response.headers.setdefault("Cache-Control", "no-cache")
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health")
def health():
    from spendtrack.store import Store

    store: Store | None = None
    try:
        store = Store()
        n = store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        return {"status": "ok", "transactions": n}
    except Exception:  # noqa: BLE001
        raise HTTPException(503, detail="db unavailable") from None
    finally:
        if store is not None:
            store.close()


@app.get("/health/data")
def health_data():
    """Целостность данных (doctor): JSON {status, checks[]}; 503 при critical."""
    from spendtrack.doctor import run_checks

    report = run_checks()
    code = 503 if report["status"] == "critical" else 200
    return JSONResponse(report, status_code=code)


def main() -> None:
    import uvicorn

    ensure_config_dir()
    _setup_logging()
    uvicorn.run(app, host="127.0.0.1", port=cfg.port, log_config=None)


if __name__ == "__main__":
    main()