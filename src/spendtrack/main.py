from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from spendtrack import errors
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Лог-настройка при старте приложения, а не на импорте модуля (ревью web_api):
    `import spendtrack.main` (pytest/CLI/IDE) больше не создаёт <data>/logs и не трогает
    uvicorn-логгеры; `uvicorn spendtrack.main:app` без main() логи получает через lifespan."""
    ensure_config_dir()
    _setup_logging()
    yield


app = FastAPI(title="Spendtrack", version="0.1.0", lifespan=_lifespan)
# DNS-rebinding/Host-атаки: loopback-имена (порт Starlette отбрасывает сам) + в Codespaces —
# домен форвардинга портов (прокси сохраняет публичный Host; см. spendtrack.security.trusted_hosts).
# "testserver" — Host по умолчанию у FastAPI TestClient (в тестах); публично не резолвится.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts())
app.include_router(frontend_router)
app.include_router(settings_router)
app.include_router(api_router, prefix="/api")

app.mount("/static", StaticFiles(directory=PKG_DIR / "static"), name="static")

logger = logging.getLogger("spendtrack")


def _error_page(message: str, status: int) -> HTMLResponse:
    """Минимальная HTML-страница для «браузерных» сбоев (W1 ресёрча ошибок)."""
    return HTMLResponse(
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f"<title>Ошибка {status}</title></head>"
        '<body style="font-family:system-ui;padding:2rem;max-width:36rem">'
        f'<h1 style="font-size:1.1rem">Ошибка {status}</h1>'
        f'<p role="alert">{message}</p>'
        '<p><a href="/">На главную</a></p></body></html>',
        status_code=status,
    )


def _wants_json(request: Request) -> bool:
    return (request.headers.get("hx-request", "").lower() == "true"
            or request.url.path.startswith("/api"))


@app.exception_handler(sqlite3.OperationalError)
async def _db_operational_error(request: Request, exc: sqlite3.OperationalError):
    """W1 ресёрча ошибок: занятая/недоступная БД — 503 с человеческим текстом, а не 500."""
    logger.warning("db operational error: %s %s: %s", request.method, request.url.path, exc)
    detail = errors.text("db_busy")
    if _wants_json(request):
        return JSONResponse({"detail": detail}, status_code=503)
    return _error_page(detail, 503)


@app.exception_handler(Exception)
async def _unhandled_error(request: Request, exc: Exception):
    """W1 ресёрча ошибок: 500 с понятным телом; в лог — метод/путь/тип (без query и тела)."""
    logger.error("unhandled error: %s %s: %s", request.method, request.url.path,
                 type(exc).__name__, exc_info=exc)
    detail = errors.text("internal")
    if _wants_json(request):
        return JSONResponse({"detail": detail}, status_code=500)
    return _error_page(detail, 500)

# Минимальный CSP для локального приложения: ограничиваем источники/встраивание.
# script-src — строго 'self': inline-скрипты и hx-on::* вынесены в /static/app.js (см. base.html),
# htmx.config.allowEval=false. style-src 'unsafe-inline' остаётся: inline-стили цветов категорий и темы.
# Сборка строки — spendtrack.security.content_security_policy() (в Codespaces добавляется
# frame-ancestors для Simple Browser редактора).


@app.middleware("http")
async def _origin_guard(request, call_next):
    """Кросс-сайтовые state-changing запросы — 403 (см. spendtrack.security)."""
    if request.method not in SAFE_METHODS and not origin_allowed(
            request.headers.get("origin"), request.headers.get("sec-fetch-site"),
            request.headers.get("host")):
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


_DOCTOR_TTL_S = 10.0
_FRESH_MIN_S = 2.0  # F7: ?fresh=1 чаще, чем раз в 2 с, не пересчитывает (анти-амплификатор)
_doctor_cache: dict = {"ts": 0.0, "report": None, "key": None}
_doctor_lock = threading.Lock()


def _doctor_key() -> tuple[str, str]:
    """Кэш doctor привязан к БД: смена SPENDTRACK_DB_PATH (тесты/CLI) не отдаёт отчёт о чужой БД."""
    return str(resolve_data_dir()), os.environ.get("SPENDTRACK_DB_PATH", "")


@app.get("/health/data")
def health_data(fresh: int = 0):
    """Целостность данных (doctor): JSON {status, checks[]}; 503 при critical.

    TTL-кэш 10 с (аудит 24.09): неаутентифицированный GET не должен каждый раз гонять
    quick_check по всей БД и sha256 offsite-копии; `?fresh=1` — принудительный пересчёт,
    но не чаще `_FRESH_MIN_S` (F7: иначе открытая страница может дёргать его в цикле).
    Lock сериализует пересчёты (два одновременных запроса не гоняют run_checks дважды).
    """
    import time

    from spendtrack.doctor import run_checks

    now = time.monotonic()
    key = _doctor_key()
    with _doctor_lock:
        hit = _doctor_cache["key"] == key and _doctor_cache["report"] is not None
        if fresh and hit and now - _doctor_cache["ts"] < _FRESH_MIN_S:
            fresh = 0  # повторный fresh — из кэша
        if fresh or not hit or now - _doctor_cache["ts"] > _DOCTOR_TTL_S:
            _doctor_cache["report"] = run_checks()
            _doctor_cache["ts"] = now
            _doctor_cache["key"] = key
    report = _doctor_cache["report"]
    code = 503 if report["status"] == "critical" else 200
    return JSONResponse(report, status_code=code)


def main() -> None:
    import uvicorn

    ensure_config_dir()
    _setup_logging()
    uvicorn.run(app, host="127.0.0.1", port=cfg.port, log_config=None)


if __name__ == "__main__":
    main()