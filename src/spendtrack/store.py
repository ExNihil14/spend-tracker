from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from spendtrack.config import ROOT
from spendtrack.config import settings as load_settings


def parse_amount(value: str | float) -> int:
    """Сумма в копейках (INTEGER). -123.45 руб → -12345. Округление HALF_UP."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value * 100
    s = str(value).replace(",", ".").replace(" ", "").replace("\u00a0", "")
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    d = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def fmt_amount(kopecks: int) -> str:
    sign = "-" if kopecks < 0 else ""
    return f"{sign}{abs(kopecks) / 100:.2f}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _norm_desc(desc: str) -> str:
    return " ".join(desc.upper().split())


def fingerprint(date: str, amount_kopecks: int, desc: str, account_anon: str, export_rowid: str) -> str:
    """sha1; export_rowid НЕ обязателен — дедуп без него работает."""
    raw = f"{date}|{amount_kopecks}|{_norm_desc(desc)}|{account_anon}|{export_rowid or ''}".encode()
    return hashlib.sha1(raw).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  description TEXT NOT NULL,
  amount_kopecks INTEGER NOT NULL,
  category TEXT NOT NULL,
  category_source TEXT NOT NULL,      -- rule | llm | import | manual | correction
  confidence REAL NOT NULL DEFAULT 1.0,
  merchant TEXT,
  account_anon TEXT,
  import_batch TEXT,
  fingerprint TEXT UNIQUE,
  created TEXT NOT NULL,
  updated TEXT NOT NULL,
  category_llm TEXT,                  -- предложение LLM (не перезаписывается = diff)
  review_status TEXT NOT NULL DEFAULT 'approved',   -- pending | approved | skipped
  statement_order INTEGER             -- порядок строки в выписке (сортировка внутри дня)
);

CREATE TABLE IF NOT EXISTS categories(
  name TEXT PRIMARY KEY,
  color TEXT NOT NULL DEFAULT '#9ca3af'
);

CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY,
  pattern TEXT NOT NULL,
  category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS examples(
  id INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  amount_kopecks INTEGER NOT NULL,
  category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches(
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  sha TEXT NOT NULL,
  nrows INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ok',
  created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_pseudonyms(
  original TEXT PRIMARY KEY,
  pseudonym TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS merchant_cache(
  key TEXT PRIMARY KEY,               -- sha1(merchant|category-unknown-key)
  merchant TEXT NOT NULL,
  category TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_merchant ON transactions(merchant);
"""


SCHEMA_VERSION = 3  # текущая версия схемы (см. Store._migrate)


class Store:
    def __init__(self, db_path: Path | None = None):
        cfg = load_settings()
        self.path = db_path or cfg.db_path or (ROOT / "data" / "spend.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    # ---- версионированные миграции (PRAGMA user_version + журнал) ----
    def _user_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def _mark_migration(self, version: int) -> None:
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations("
            " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?,?)",
            (version, _now_iso()))
        self.conn.execute(f"PRAGMA user_version = {int(version)}")

    def _migrate(self) -> None:
        """Версии: 1 — базовая схема; 2 — Work 3 (category_llm/review_status + бэкфилл); 3 — statement_order."""
        if self._user_version() < 1:
            self._mark_migration(1)
        if self._user_version() < 2:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(transactions)")}
            if "review_status" not in cols:
                self.conn.execute("ALTER TABLE transactions ADD COLUMN category_llm TEXT")
                self.conn.execute(
                    "ALTER TABLE transactions ADD COLUMN review_status TEXT NOT NULL DEFAULT 'approved'")
                # Бэкфилл только при реальном апгрейде старой схемы (иначе откатывает skip/approve).
                self.conn.execute(
                    "UPDATE transactions SET review_status='pending'"
                    " WHERE category_source='llm_pending_review'")
                self.conn.execute(
                    "UPDATE transactions SET category_llm=category"
                    " WHERE category_source IN ('llm','llm_pending_review') AND category_llm IS NULL")
            self._mark_migration(2)
        if self._user_version() < 3:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(transactions)")}
            if "statement_order" not in cols:
                self.conn.execute("ALTER TABLE transactions ADD COLUMN statement_order INTEGER")
            self._mark_migration(3)

    def close(self) -> None:
        self.conn.close()

    # ---- account pseudonymization ----
    def pseudonymize(self, original: str | None) -> str | None:
        if not original or not original.strip():
            return None
        original = original.strip()
        row = self.conn.execute("SELECT pseudonym FROM account_pseudonyms WHERE original=?", (original,)).fetchone()
        if row:
            return row["pseudonym"]
        p = "acc_" + uuid.uuid4().hex[:8]
        self.conn.execute("INSERT INTO account_pseudonyms(original, pseudonym) VALUES(?,?)", (original, p))
        self.conn.commit()
        return p

    # ---- transaction CRUD ----
    def add_transaction(
        self,
        date: str,
        description: str,
        amount_kopecks: int,
        category: str,
        category_source: str,
        confidence: float = 1.0,
        merchant: str | None = None,
        account_anon: str | None = None,
        import_batch: str | None = None,
        export_rowid: str = "",
        category_llm: str | None = None,
        review_status: str = "approved",
        statement_order: int | None = None,
    ) -> int | None:
        fp = fingerprint(date, amount_kopecks, description, account_anon or "", export_rowid)
        existing = self.conn.execute("SELECT id FROM transactions WHERE fingerprint=?", (fp,)).fetchone()
        if existing:
            return None
        now = _now_iso()
        cur = self.conn.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
            " confidence, merchant, account_anon, import_batch, fingerprint, created, updated,"
            " category_llm, review_status, statement_order)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, description, amount_kopecks, category, category_source, confidence,
             merchant, account_anon, import_batch, fp, now, now, category_llm, review_status,
             statement_order),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_category(self, tx_id: int, category: str, source: str = "correction") -> bool:
        cur = self.conn.execute(
            "UPDATE transactions SET category=?, category_source=?, updated=? WHERE id=?",
            (category, source, _now_iso(), tx_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def pending_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE review_status='pending'").fetchone()
        return row["c"]

    def approve_review(self, tx_id: int, category: str) -> bool:
        """Человек подтвердил предложенную категорию (или переопределил)."""
        cur = self.conn.execute(
            "UPDATE transactions SET category=?, category_source='rule', review_status='approved',"
            " updated=? WHERE id=? AND review_status='pending'",
            (category, _now_iso(), tx_id),
        )
        self.conn.commit()
        if cur.rowcount:
            self.seed_merchant_cache(tx_id)
        return cur.rowcount > 0

    def skip_review(self, tx_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE transactions SET review_status='skipped', updated=? WHERE id=? AND review_status='pending'",
            (_now_iso(), tx_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def approve_all_reviews(self) -> int:
        cur = self.conn.execute(
            "UPDATE transactions SET category=COALESCE(category_llm, category, 'other'),"
            " category_source='rule', review_status='approved', updated=? WHERE review_status='pending'",
            (_now_iso(),),
        )
        self.conn.commit()
        return cur.rowcount

    def update_merchant(self, tx_id: int, merchant: str | None) -> None:
        self.conn.execute("UPDATE transactions SET merchant=?, updated=? WHERE id=?",
                          (merchant, _now_iso(), tx_id))
        self.conn.commit()

    def list_transactions(self, month: str | None = None, category: str | None = None,
                          needs_review: bool = False, limit: int = 500,
                          search: str | None = None, sort: str = "recent") -> list[dict]:
        sql = "SELECT * FROM transactions WHERE 1=1"
        params: list[str] = []
        if month:
            sql += " AND substr(date,1,7)=?"
            params.append(month)
        if category:
            sql += " AND category=?"
            params.append(category)
        if search:
            sql += " AND (description LIKE ? OR merchant LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like])
        if needs_review:
            sql += " AND review_status='pending'"
        if needs_review:
            sql += " ORDER BY date ASC, amount_kopecks DESC, id ASC LIMIT ?"
        elif sort == "amount":
            # «Крупные сначала»: по модулю суммы, свежие — при равенстве
            sql += " ORDER BY ABS(amount_kopecks) DESC, date DESC, id DESC LIMIT ?"
        else:
            # recent: внутри дня — порядок строк выписки (statement_order), иначе id
            sql += " ORDER BY date DESC, COALESCE(statement_order, id) DESC, id DESC LIMIT ?"
        params.append(str(limit))
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_transaction(self, tx_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        return dict(row) if row else None

    def queued_for_review(self) -> list[dict]:
        return self.list_transactions(needs_review=True)

    def list_transactions_days(
        self,
        month: str | None = None,
        category: str | None = None,
        search: str | None = None,
        days: int = 31,
        after_date: str | None = None,
    ) -> tuple[list[dict], str | None, bool]:
        """Keyset-страница ЦЕЛЫМИ днями (для больших списков): (rows, next_after, has_more).

        Пагинация по датам (`date < after_date`), а не по строкам — дневные итоги и
        группировка не разрезаются. Сортировка внутри дня: statement_order, иначе id.
        """
        where, params = [], []
        if month:
            where.append("substr(date,1,7)=?")
            params.append(month)
        if category:
            where.append("category=?")
            params.append(category)
        if search:
            where.append("(description LIKE ? OR merchant LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if after_date:
            where.append("date < ?")
            params.append(after_date)
        clause = (" WHERE " + " AND ".join(where)) if where else ""

        dates = [
            r["date"]
            for r in self.conn.execute(
                f"SELECT DISTINCT date FROM transactions{clause} ORDER BY date DESC LIMIT ?",
                [*params, str(days + 1)],
            )
        ]
        has_more = len(dates) > days
        dates = dates[:days]
        if not dates:
            return [], None, False

        placeholders = ",".join("?" * len(dates))
        rows = self.conn.execute(
            f"SELECT * FROM transactions WHERE date IN ({placeholders})"
            " ORDER BY date DESC, COALESCE(statement_order, id) DESC, id DESC",
            dates,
        ).fetchall()
        return [dict(r) for r in rows], dates[-1], has_more

    # ---- category cache by merchant ----
    class MerchantCacheEntry:
        pass

    def merchant_cache_get(self, merchant: str) -> str | None:
        if not merchant:
            return None
        key = hashlib.sha1(merchant.upper().encode()).hexdigest()
        row = self.conn.execute("SELECT category FROM merchant_cache WHERE key=?", (key,)).fetchone()
        return row["category"] if row else None

    def merchant_cache_set(self, merchant: str, category: str) -> None:
        key = hashlib.sha1(merchant.upper().encode()).hexdigest()
        self.conn.execute(
            "INSERT INTO merchant_cache(key, merchant, category, updated) VALUES(?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET category=excluded.category, updated=excluded.updated",
            (key, merchant, category, _now_iso()),
        )
        self.conn.commit()

    def seed_merchant_cache(self, tx_id: int) -> None:
        """Запоминает категорию по мерчанту после правки юзера (few-shot loop)."""
        row = self.conn.execute(
            "SELECT merchant, category FROM transactions WHERE id=? AND merchant IS NOT NULL", (tx_id,)
        ).fetchone()
        if row and row["merchant"]:
            self.merchant_cache_set(row["merchant"], row["category"])

    # ---- examples (few-shot) ----
    def add_example(self, description: str, amount_kopecks: int, category: str) -> None:
        self.conn.execute("INSERT INTO examples(description, amount_kopecks, category) VALUES(?,?,?)",
                          (description, amount_kopecks, category))
        self.conn.commit()

    def list_examples(self, limit: int = 8) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM examples ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---- import batches ----
    def add_batch(self, filename: str, sha: str, nrows: int) -> str:
        batch_id = "b_" + uuid.uuid4().hex[:10]
        self.conn.execute(
            "INSERT INTO import_batches(id, filename, sha, nrows, created) VALUES(?,?,?,?,?)",
            (batch_id, filename, sha, nrows, _now_iso()),
        )
        self.conn.commit()
        return batch_id

    def counts(self) -> dict:
        rows = self.conn.execute(
            "SELECT category_source, COUNT(*) c FROM transactions GROUP BY category_source"
        ).fetchall()
        return {r["category_source"]: r["c"] for r in rows}