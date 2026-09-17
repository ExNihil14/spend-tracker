"""Doctor: проверки целостности данных (offline-first, read-only по смыслу).

CLI: `uv run spendtrack doctor [--json]`; API: `GET /health/data`.
Правила (дизайн 16.09): critical — битая БД/схема/категории транзакций;
warn — данные вне очереди/таксономии, старый бэкап; info — пустые партии,
отсутствие папки бэкапов. Никакого авторемонта и записи (кроме миграций Store).
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from spendtrack.config import ROOT, load_settings
from spendtrack.store import SCHEMA_VERSION, Store
from spendtrack.taxonomy import Taxonomy, load_taxonomy

CRITICAL = "critical"
WARN = "warn"
INFO = "info"
OK = "ok"

_DETAIL_ITEMS = 5
_BACKUP_STALE = timedelta(hours=48)


def _check(check_id: str, severity: str, count: int = 0, detail: str = "") -> dict[str, Any]:
    return {"id": check_id, "severity": severity, "count": int(count), "detail": detail}


def _names(taxonomy: Taxonomy) -> tuple[list[str], str]:
    names = sorted({c.name for c in taxonomy.categories})
    return names, ",".join("?" * len(names))


def _summary(rows: list[sqlite3.Row], key: str) -> str:
    items = [f"{rows[i][key]}×{rows[i]['n']}" for i in range(min(len(rows), _DETAIL_ITEMS))]
    if len(rows) > _DETAIL_ITEMS:
        items.append("…")
    return ", ".join(items)


# ---- 1. целостность страниц ----
def check_quick_check(conn: sqlite3.Connection) -> dict:
    try:
        rows = conn.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as e:
        # Структурная порча часто роняет сам PRAGMA («database disk image is malformed»),
        # а не отдаёт строки-ошибки — это тот же critical, но с другим текстом.
        return _check("quick_check", CRITICAL, 1, f"quick_check не выполнился: {e}")
    problems = [str(r[0]) for r in rows if str(r[0]) != "ok"]
    if not problems:
        return _check("quick_check", OK, 0, "база целостна")
    lines = [ln.strip() for p in problems for ln in p.splitlines() if ln.strip()]
    return _check("quick_check", CRITICAL, max(len(lines), 1), "; ".join(lines)[:200])


# ---- 2. дубли fingerprint ----
def check_fingerprint_dupes(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT fingerprint, COUNT(*) n FROM transactions WHERE fingerprint IS NOT NULL"
        " GROUP BY fingerprint HAVING COUNT(*) > 1 ORDER BY n DESC").fetchall()
    if not rows:
        return _check("fingerprint_dupes", OK, 0, "дубликатов нет")
    total = sum(r["n"] - 1 for r in rows)
    items = [f"{rows[i]['fingerprint'][:10]}…×{rows[i]['n']}" for i in range(min(len(rows), _DETAIL_ITEMS))]
    if len(rows) > _DETAIL_ITEMS:
        items.append("…")
    return _check("fingerprint_dupes", CRITICAL, total, "дубли: " + ", ".join(items))


# ---- 3. версия схемы ----
def check_schema_version(conn: sqlite3.Connection) -> dict:
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version != SCHEMA_VERSION:
        return _check("schema_version", CRITICAL, 1,
                      f"user_version={version}, ожидается {SCHEMA_VERSION}")
    return _check("schema_version", OK, 0, f"user_version={version}")


# ---- 4. категории вне таксономии ----
def check_categories_invalid(conn: sqlite3.Connection, names: list[str], ph: str) -> dict:
    rows = conn.execute(
        f"SELECT category, COUNT(*) n FROM transactions WHERE category NOT IN ({ph})"
        " GROUP BY category ORDER BY n DESC", names).fetchall()
    count = sum(r["n"] for r in rows)
    if count:
        return _check("categories_invalid", CRITICAL, count,
                      "category вне таксономии: " + _summary(rows, "category"))
    return _check("categories_invalid", OK, 0, "все category в таксономии")


def check_category_llm_invalid(conn: sqlite3.Connection, names: list[str], ph: str) -> dict:
    rows = conn.execute(
        f"SELECT category_llm, COUNT(*) n FROM transactions"
        f" WHERE category_llm IS NOT NULL AND category_llm != ''"
        f" AND category_source != 'llm_pending_review' AND category_llm NOT IN ({ph})"
        " GROUP BY category_llm ORDER BY n DESC", names).fetchall()
    count = sum(r["n"] for r in rows)
    if count:
        return _check("category_llm_invalid", WARN, count,
                      "category_llm вне таксономии (не pending): " + _summary(rows, "category_llm"))
    return _check("category_llm_invalid", OK, 0, "category_llm вне таксономии нет")


def check_refs_invalid(conn: sqlite3.Connection, names: list[str], ph: str) -> dict:
    # `category IS NULL` — реальный кейс для budgets (SQLite: TEXT PRIMARY KEY допускает NULL);
    # остальные колонки NOT NULL, но предикат общий и безвредный.
    counts = {
        table: conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE category NOT IN ({ph}) OR category IS NULL",
            names).fetchone()[0]
        for table in ("rules", "budgets", "merchant_cache", "examples")
    }
    total = sum(counts.values())
    detail = ", ".join(f"{k}={v}" for k, v in counts.items())
    if total:
        return _check("refs_invalid", WARN, total, f"ссылки на неизвестные категории: {detail}")
    return _check("refs_invalid", OK, 0, "rules/budgets/merchant_cache/examples согласованы")


# ---- 5. pending с чужим источником ----
def check_pending_source(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT id, category_source FROM transactions"
        " WHERE review_status='pending' AND category_source != 'llm_pending_review'"
        " ORDER BY id").fetchall()
    if not rows:
        return _check("pending_source", OK, 0, "pending только от llm_pending_review")
    sample = ", ".join(f"id={rows[i]['id']} ({rows[i]['category_source']})"
                       for i in range(min(len(rows), _DETAIL_ITEMS)))
    return _check("pending_source", WARN, len(rows),
                  f"pending с источником ≠ llm_pending_review: {sample}")


# ---- 6. пустые партии импорта ----
def check_empty_batches(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT b.id FROM import_batches b"
        " WHERE NOT EXISTS (SELECT 1 FROM transactions t WHERE t.import_batch = b.id)"
        " ORDER BY b.created").fetchall()
    if not rows:
        return _check("empty_batches", OK, 0, "пустых партий нет")
    sample = ", ".join(rows[i]["id"] for i in range(min(len(rows), _DETAIL_ITEMS)))
    return _check("empty_batches", INFO, len(rows), f"партии без транзакций: {sample}")


# ---- 7. бэкапы (scripts/backup.py → data/backup/spend-*.db) ----
def check_backup(db_path: Path) -> dict:
    backup_dir = db_path.parent / "backup"
    files = sorted(backup_dir.glob("spend-*.db"), key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        return _check("backup", INFO, 0, f"бэкапов нет ({backup_dir})")
    newest = files[-1]
    mtime = datetime.fromtimestamp(newest.stat().st_mtime, UTC)
    age = datetime.now(UTC) - mtime
    hours = age.total_seconds() / 3600
    problem = _snapshot_quick_check(newest)
    if problem:
        return _check("backup", CRITICAL, len(files), f"бэкап {newest.name} повреждён: {problem}")
    if age > _BACKUP_STALE:
        return _check("backup", WARN, len(files),
                      f"последний бэкап {newest.name} старше 48ч ({hours:.0f}ч)")
    return _check("backup", OK, len(files), f"последний бэкап: {newest.name} ({hours:.0f}ч назад)")


def _snapshot_quick_check(path: Path) -> str | None:
    """quick_check снимка + «снимок не пустой»: файл 0 байт прошёл бы quick_check как пустая БД."""
    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        rows = con.execute("PRAGMA quick_check").fetchall()
        has_tx = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()[0]
    except sqlite3.Error as e:
        return str(e)[:200]
    finally:
        if con is not None:
            con.close()
    problems = [str(r[0]) for r in rows if str(r[0]) != "ok"]
    if problems:
        return problems[0].splitlines()[0].strip()[:200]
    if not has_tx:
        return "в снимке нет таблицы transactions"
    return None


def _guarded(check_id: str, fn) -> dict:
    """Битая БД/нет доступа/неожиданная ошибка чтения — чек становится critical, прогон не падает.

    Ловим и не-sqlite исключения (Exception): на повреждённых данных SQLite может отдать
    None/мусор, и конкретная проверка падает TypeError'ом (найдено стрессом 17.09).
    """
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — контракт: упавший чек = critical, doctor не роняем
        return _check(check_id, CRITICAL, 1, f"не удалось выполнить проверку: {type(e).__name__}: {e}")


def overall_status(checks: list[dict]) -> str:
    severities = {c["severity"] for c in checks}
    if CRITICAL in severities:
        return CRITICAL
    if WARN in severities:
        return WARN
    return OK


def run_checks(db_path: Path | str | None = None, taxonomy: Taxonomy | None = None) -> dict[str, Any]:
    """Полный прогон; возвращает {status, checks:[{id, severity, count, detail}]}."""
    cfg = load_settings()
    path = Path(db_path or cfg.db_path or ROOT / "data" / "spend.db").expanduser().resolve()
    try:
        tax = taxonomy if taxonomy is not None else load_taxonomy()
    except Exception as e:  # noqa: BLE001 — битый taxonomy.toml = critical
        return {"status": CRITICAL,
                "checks": [_check("taxonomy_config", CRITICAL, 1, f"taxonomy.toml: {e}")]}
    try:
        store = Store(path)
    except sqlite3.Error as e:
        return {"status": CRITICAL,
                "checks": [_check("db_open", CRITICAL, 1, f"не удалось открыть БД: {e}")]}
    try:
        conn = store.conn
        names, ph = _names(tax)
        checks = [
            _guarded("quick_check", lambda: check_quick_check(conn)),
            _guarded("fingerprint_dupes", lambda: check_fingerprint_dupes(conn)),
            _guarded("schema_version", lambda: check_schema_version(conn)),
            _guarded("categories_invalid", lambda: check_categories_invalid(conn, names, ph)),
            _guarded("category_llm_invalid", lambda: check_category_llm_invalid(conn, names, ph)),
            _guarded("refs_invalid", lambda: check_refs_invalid(conn, names, ph)),
            _guarded("pending_source", lambda: check_pending_source(conn)),
            _guarded("empty_batches", lambda: check_empty_batches(conn)),
            _guarded("backup", lambda: check_backup(path)),
        ]
    finally:
        store.close()
    return {"status": overall_status(checks), "checks": checks}
