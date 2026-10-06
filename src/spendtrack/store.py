from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from datetime import date as _date_cls
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from spendtrack import errors
from spendtrack.config import base_currency, resolve_data_dir
from spendtrack.config import settings as load_settings

# Санитарный предел суммы на операцию (1 млрд руб в копейках) — общий для импорта/API/Store
# (ревью wave5, S4: form-путь целей не должен принимать больше JSON-пути). csv_import реэкспортирует.
MAX_AMOUNT_KOPECKS = 100_000_000_000

logger = logging.getLogger(__name__)


def parse_amount(value: str | float) -> int:
    """Сумма в копейках (INTEGER). -123.45 руб → -12345. Округление HALF_UP.

    Неразбираемое/не-число (включая NaN/Infinity из текста) — контролируемая `InvalidOperation`:
    вызывающие (API/импорт/CLI) переводят её в 422/пропуск/ошибку, а не в трейсбек.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value * 100
    s = str(value).replace(",", ".").replace(" ", "").replace("\u00a0", "")
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    d = Decimal(s)
    if not d.is_finite():  # «nan», «inf», «-infinity» — Decimal их принимает, но это не деньги
        raise InvalidOperation(errors.text("not_a_number", value=value))
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def fmt_amount(kopecks: int) -> str:
    """Машинная форма (ASCII-минус, без плюса): CSV/экспорт, промпты, CLI."""
    sign = "-" if kopecks < 0 else ""
    return f"{sign}{abs(kopecks) / 100:.2f}"


def fmt_amount_signed(kopecks: int) -> str:
    """Отображаемая форма с явным знаком: «−123.45» / «+123.45» (ноль — «0.00»).

    Типографский минус U+2212; знак обязателен, чтобы цвет не был единственным
    носителем смысла «доход/расход» (WCAG 1.4.1). Для CSV/промптов — `fmt_amount`.
    """
    if kopecks == 0:
        return "0.00"
    sign = "\u2212" if kopecks < 0 else "+"
    return f"{sign}{abs(kopecks) / 100:.2f}"


def _group_digits(digits: str) -> str:
    """«155365» → «155 365» (неразрывные пробелы — число не рвётся переносом)."""
    parts: list[str] = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return "\u00a0".join(parts)


_MONEY_SYMBOLS = MappingProxyType({"RUB": "₽", "BYN": "Br"})


def currency_symbol(currency: str | None = None) -> str:
    """Символ валюты для UI: «₽»/«Br» для известных, иначе ISO-код (единая точка для fmt_money/JS)."""
    cur = (currency or base_currency()).upper()
    return _MONEY_SYMBOLS.get(cur, cur)


def fmt_money(kopecks: int, currency: str | None = None, signed: bool = True) -> str:
    """Денежная форма для UI: «−155 365,18 ₽» / «+45 000,00 Br» (ноль — «0,00 ₽»).

    Знак — U+2212 (WCAG 1.4.1), разряды — неразрывный пробел, десятичная запятая; валюта по
    умолчанию — базовая из настроек, известные символы (₽/Br), иначе — код валюты.
    `signed=False` — без «+» у положительных (лимиты/суммы без направления: бюджеты, перерасход).
    Машинные формы — `fmt_amount`.
    """
    if kopecks == 0:
        sign = ""
    elif kopecks < 0:
        sign = "\u2212"
    else:
        sign = "+" if signed else ""
    whole, frac = divmod(abs(int(kopecks)), 100)
    return f"{sign}{_group_digits(str(whole))},{frac:02d} {currency_symbol(currency)}"


_MONTHS_RU = ("", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")


def fmt_month(month: str) -> str:
    """«2026-09» → «Сентябрь 2026»; невалидное значение — как есть (UI-подпись месяца)."""
    try:
        year, num = month.split("-")
        return f"{_MONTHS_RU[int(num)]} {year}"
    except (ValueError, IndexError):
        return month


def fmt_date(iso_date: str) -> str:
    """«2026-09-13» → «13.09» (компактно для таблиц; ISO остаётся в экспорте/API)."""
    try:
        _, month, day = iso_date.split("-")
        return f"{day}.{month}"
    except ValueError:
        return iso_date


def conf_level(confidence: float) -> str:
    """Уровень уверенности для очереди текстом: «низкая» / «средняя» / «высокая».

    Дизайн-ревью M-4: процент в UI читается хуже уровня, а «0%» выглядел как сбой.
    """
    if confidence < 0.5:
        return "низкая"
    if confidence < 0.7:
        return "средняя"
    return "высокая"


def delta_words(delta_k: int) -> str:
    """Дельта расходов словами (дизайн-ревью M-5): «↑ на 6 925,00 ₽» / «↓ на …» / «без изменений».

    Семантика расходная: `delta_k` — изменение знаковой суммы расходов (отрицательные);
    рост трат → `↑`, снижение → `↓`. Вместо «Δ −6925.00» — направление словом и модуль суммы.
    """
    if delta_k == 0:
        return "без изменений"
    arrow = "↑ на" if delta_k < 0 else "↓ на"
    return f"{arrow} {fmt_money(abs(delta_k), signed=False)}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


_CURRENCY_ALIASES = MappingProxyType({
    "RUB": "RUB", "RUR": "RUB", "РУБ": "RUB", "РУБ.": "RUB", "₽": "RUB",
    "USD": "USD", "US$": "USD", "$": "USD", "ДОЛЛАР": "USD", "ДОЛЛАРОВ": "USD",
    "EUR": "EUR", "€": "EUR", "ЕВРО": "EUR",
    "KZT": "KZT", "₸": "KZT", "ТЕНГЕ": "KZT",
    "BYN": "BYN", "БЕЛРУБ": "BYN", "БЕЛ.РУБ": "BYN",
    "UAH": "UAH", "₴": "UAH", "ГРИВНА": "UAH", "ГРИВЕН": "UAH",
    "GBP": "GBP", "£": "GBP", "ФУНТ": "GBP",
    "TRY": "TRY", "₺": "TRY", "ЛИРА": "TRY",
    "CNY": "CNY", "ЮАНЬ": "CNY", "ЖЭНЬМИНЬБИ": "CNY",
    "JPY": "JPY", "ИЕНА": "JPY",
    "GEL": "GEL", "₾": "GEL", "ЛАРИ": "GEL",
    "AMD": "AMD", "֏": "AMD", "ДРАМ": "AMD",
    "KGS": "KGS", "СОМ": "KGS",
    "UZS": "UZS", "СУМ": "UZS",
    "AZN": "AZN", "₼": "AZN", "МАНАТ": "AZN",
    "PLN": "PLN", "ZŁ": "PLN", "ЗЛОТЫЙ": "PLN",
    "CHF": "CHF", "AED": "AED", "THB": "THB", "฿": "THB",
    "INR": "INR", "₹": "INR", "VND": "VND", "₫": "VND",
})


def normalize_currency(value: str | None) -> str | None:
    """Код валюты ISO 4217 из строки банка/пользователя: «₽»/«руб.»/«rub» → RUB.

    Не распознано (или пусто) → None: импорт трактует как RUB (базовая валюта),
    API/CLI — как ошибку ввода (пользователь не должен получить молчаливую подмену).
    """
    if value is None:
        return None
    v = str(value).strip().upper().replace(" ", "").replace("\u00a0", "")
    if not v:
        return None
    if v in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[v]
    v = v.rstrip(".")
    if v in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[v]
    if len(v) == 3 and v.isascii() and v.isalpha():
        return v
    return None



def _norm_desc(desc: str) -> str:
    return " ".join(desc.upper().split())


_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# wave5 №6: ASCII-цифры + fullmatch — `\d` матчил не-ASCII цифры, а `$`+match — «2026-09-01\n»;
# строки проходили Python-валидацию и падали на SQL CHECK (IntegrityError вместо ValueError).
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def valid_month(month: str | None) -> bool:
    """True для «YYYY-MM» с реальным месяцем 01..12 (query/CLI-валидация; иначе — 500, аудит 24.09)."""
    return bool(month and _MONTH_RE.match(month))


def month_bounds(month: str) -> tuple[str, str]:
    """Границы месяца для индексного фильтра: («2026-09-01», «2026-10-01»).

    `substr(date,1,7)=?` не использует индекс по `date`; диапазон — использует (замеры: bench.py).
    """
    if not valid_month(month):
        raise ValueError(f"некорректный месяц: {month!r} (ожидается YYYY-MM)")
    y, m = int(month[:4]), int(month[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"


def fingerprint(date: str, amount_kopecks: int, desc: str, account_anon: str, export_rowid: str,
                currency: str = "RUB") -> str:
    """sha1; export_rowid НЕ обязателен — дедуп без него работает.

    Валюта входит в отпечаток только для НЕ-RUB (base-НЕзависимо, ревью wave5 C1): отпечатки
    не меняются при смене `base_currency` (повторный импорт старой выписки остаётся no-op),
    а одинаковые суммы в разных валютах не склеиваются дедупом.
    """
    raw = f"{date}|{amount_kopecks}|{_norm_desc(desc)}|{account_anon}|{export_rowid or ''}"
    if currency != "RUB":
        raw += f"|{currency}"
    return hashlib.sha1(raw.encode()).hexdigest()


# Схема transactions — единый источник: fresh-БД и пересборка таблицы в _migrate_v6 (CHECK(date), тикет 03.10).
_TX_DDL = """
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),  -- v6: щит слоя данных
  description TEXT NOT NULL,
  amount_kopecks INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'RUB',  -- ISO 4217; не-RUB не попадает в ₽-итоги/бюджеты
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
"""

# v7 (03.10): цели/копилки — «виртуальный конверт» (research 03.10). Деньги физически
# не двигаются; взносы append-only и подписанные (изъятие = отрицательный), прогресс — на лету.
# STRICT+CHECK — щит нового слоя; цель не удаляется (архив), FK ON DELETE RESTRICT.
# v8 (06.10, wave5 №3): предел суммы взноса в CHECK — интерполяция MAX_AMOUNT_KOPECKS (единый лимит).
_GOALS_DDL = f"""
CREATE TABLE IF NOT EXISTS goals(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
  target_kopecks INTEGER NOT NULL CHECK(target_kopecks > 0),
  currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency GLOB '[A-Z][A-Z][A-Z]'),
  due_month TEXT CHECK(due_month IS NULL OR due_month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
  created_month TEXT NOT NULL CHECK(created_month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
  archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0, 1)),
  created TEXT NOT NULL,
  updated TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS goal_allocations(
  id INTEGER PRIMARY KEY,
  goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE RESTRICT,
  date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks <> 0 AND abs(amount_kopecks) <= {MAX_AMOUNT_KOPECKS}),
  reverses_id INTEGER REFERENCES goal_allocations(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_goal_alloc ON goal_allocations(goal_id, date);
"""

SCHEMA = _TX_DDL + """
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
  key TEXT PRIMARY KEY,               -- sha1(merchant.upper()); от категории НЕ зависит
  merchant TEXT NOT NULL,
  category TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets(
  category        TEXT PRIMARY KEY,            -- имя категории таксономии
  amount_kopecks  INTEGER NOT NULL CHECK(amount_kopecks > 0),
  updated         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_merchant ON transactions(merchant);
""" + _GOALS_DDL


SCHEMA_VERSION = 8  # текущая версия схемы (см. Store._migrate)


class Store:
    def __init__(self, db_path: Path | None = None):
        cfg = load_settings()
        self.path = db_path or cfg.db_path or (resolve_data_dir() / "spend.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Существовавшая БД (не первое создание) — перед миграцией делаем pre-migration-снимок (ревью install_ops, C1)
        self._did_exist = self.path.exists()
        # check_same_thread=False: sync-роуты FastAPI живут в threadpool, соединение может пересекать потоки
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")  # ждать чужую блокировку до 5с, а не падать сразу
        # WAL + synchronous=NORMAL — рекомендованный SQLite режим для WAL: fsync на checkpoint,
        # целостность БД гарантирована, теряется лишь последний коммит при крахе ОС (не процесса).
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA cache_size=-8000")  # 8 МБ кэша страниц (дефолт ~2 МБ)
        self.conn.execute("PRAGMA temp_store=MEMORY")  # temp-таблицы/индексы в RAM, меньше plaintext-temp
        try:
            if self._did_exist and self._user_version() < SCHEMA_VERSION:
                # Апгрейд существующей БД: снимок ДО SCHEMA/миграций — ровно прежнее состояние (C1, install_ops)
                self._pre_migration_snapshot()
            self.conn.executescript(SCHEMA)
            self._migrate()
            self.conn.commit()
        except BaseException:
            # Сбой инициализации (битая миграция/схема) не должен оставлять открытое соединение
            # (ревью Sonnet 5.5, 30.09) — иначе утечка на каждый неудачный старт процесса.
            self.conn.close()
            raise

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

    def _tx_columns(self) -> set[str]:
        return {r[1] for r in self.conn.execute("PRAGMA table_info(transactions)")}

    def _migrate_v2(self) -> None:
        """Work 3: очередь подтверждения; гард по каждой колонке — лечит частичное состояние."""
        cols = self._tx_columns()
        added_llm = "category_llm" not in cols
        added_status = "review_status" not in cols
        if added_llm:
            self.conn.execute("ALTER TABLE transactions ADD COLUMN category_llm TEXT")
        if added_status:
            self.conn.execute(
                "ALTER TABLE transactions ADD COLUMN review_status TEXT NOT NULL DEFAULT 'approved'")
        if added_llm or added_status:
            # Бэкфилл только при реальном апгрейде старой схемы (иначе откатывает skip/approve).
            self.conn.execute(
                "UPDATE transactions SET review_status='pending'"
                " WHERE category_source='llm_pending_review'")
            self.conn.execute(
                "UPDATE transactions SET category_llm=category"
                " WHERE category_source IN ('llm','llm_pending_review') AND category_llm IS NULL")
        self._mark_migration(2)

    def _migrate_v3(self) -> None:
        if "statement_order" not in self._tx_columns():
            self.conn.execute("ALTER TABLE transactions ADD COLUMN statement_order INTEGER")
        self._mark_migration(3)

    def _migrate_v5(self) -> None:
        if "currency" not in self._tx_columns():
            # DEFAULT 'RUB' сам бэкфиллит старые строки — рублёвые данные не меняются.
            self.conn.execute(
                "ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'RUB'")
            # Страховка для экзотических сборок SQLite, где DEFAULT не виден старым строкам.
            self.conn.execute("UPDATE transactions SET currency='RUB' WHERE currency IS NULL")
        self._mark_migration(5)

    def _migrate_v6(self) -> None:
        """CHECK(date) — щит слоя данных (out_web_api, тикет 03.10): формат YYYY-MM-DD на любой записи.

        SQLite не умеет ADD CONSTRAINT → пересборка таблицы в общей транзакции `_migrate`
        (`BEGIN IMMEDIATE`); копируем только пересечение колонок (легаси-формы различаются),
        NULL created/updated до-заполняем. Строки с датой вне формата — явный отказ
        (pre-migration-снимок уже сделан, данные не теряются).
        S3 (wave5): кастомные индексы transactions, созданные вручную, пересборка НЕ восстанавливает —
        свои idx_* создаём мы, чужие придётся создать заново (осознанный предел).
        """
        bad = self.conn.execute(
            "SELECT COUNT(*) FROM transactions"
            " WHERE date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'").fetchone()[0]
        if bad:
            samples = [r[0] for r in self.conn.execute(
                "SELECT date FROM transactions"
                " WHERE date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' LIMIT 5")]
            raise RuntimeError(
                f"миграция v6: {bad} строк с датой вне формата YYYY-MM-DD (примеры: {samples}) — "
                "исправьте данные и повторите; pre-migration-снимок лежит рядом с БД "
                "(диагностика — `spendtrack doctor`)")
        old_cols = self._tx_columns()
        now_sql = "strftime('%Y-%m-%dT%H:%M:%S+00:00','now')"
        # wave6 store S4: guard читает только ФАКТИЧЕСКИ доступные колонки (схема с created без updated
        # роняла миграцию «no such column: updated»)
        if "created" in old_cols:
            src = f"COALESCE(updated, {now_sql})" if "updated" in old_cols else now_sql
            self.conn.execute(
                f"UPDATE transactions SET created = COALESCE(created, {src}) WHERE created IS NULL")
        if "updated" in old_cols:
            src = f"COALESCE(created, {now_sql})" if "created" in old_cols else now_sql
            self.conn.execute(
                f"UPDATE transactions SET updated = COALESCE(updated, {src}) WHERE updated IS NULL")
        new_cols = ["id", "date", "description", "amount_kopecks", "currency", "category",
                    "category_source", "confidence", "merchant", "account_anon", "import_batch",
                    "fingerprint", "created", "updated", "category_llm", "review_status",
                    "statement_order"]
        copy_cols = [c for c in new_cols if c in old_cols]
        # wave6 store S4: отсутствующие created/updated — литералы в INSERT (новые колонки NOT NULL)
        insert_cols = list(copy_cols)
        select_exprs = list(copy_cols)
        for c in ("created", "updated"):
            if c not in old_cols:
                insert_cols.append(c)
                select_exprs.append(now_sql)
        cols = ", ".join(insert_cols)
        exprs = ", ".join(select_exprs)
        self.conn.execute("ALTER TABLE transactions RENAME TO transactions_pre_v6")
        self.conn.execute(_TX_DDL)
        self.conn.execute(f"INSERT INTO transactions ({cols}) SELECT {exprs} FROM transactions_pre_v6")
        self.conn.execute("DROP TABLE transactions_pre_v6")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_merchant ON transactions(merchant)")
        self._mark_migration(6)

    def _migrate_v7(self) -> None:
        """Цели/копилки (research 03.10): goals + append-only goal_allocations (STRICT+CHECK, FK RESTRICT).

        Аддитивно: старые данные не трогаются. executescript не используется — он неявно
        коммитит, ломая общий откат `_migrate`; DDL выполняется отдельными statements.
        """
        for stmt in _GOALS_DDL.split(";"):
            if stmt.strip():
                self.conn.execute(stmt)
        self._mark_migration(7)

    def _migrate_v8(self) -> None:
        """v8 (wave5 №3): CHECK предела суммы взноса для уже созданных v7-БД.

        SQLite не умеет добавить CHECK к существующей таблице — пересборка goal_allocations
        с переносом данных 1:1. Нарушающие строки (могли появиться только мимо Store) блокируют
        миграцию явной ошибкой; транзакция `_migrate` откатит всё, БД останется рабочей на v7.
        """
        bad = self.conn.execute(
            "SELECT COUNT(1) FROM goal_allocations WHERE abs(amount_kopecks) > ?",
            (MAX_AMOUNT_KOPECKS,)).fetchone()[0]
        if bad:
            raise RuntimeError(
                f"в goal_allocations {bad} строк(и) сверх лимита {MAX_AMOUNT_KOPECKS} копеек — "
                "исправьте их и запустите приложение снова (данные не тронуты)")
        self.conn.execute("DROP INDEX IF EXISTS idx_goal_alloc")
        self.conn.execute("ALTER TABLE goal_allocations RENAME TO goal_allocations_pre_v8")
        for stmt in _GOALS_DDL.split(";"):
            if stmt.strip():
                self.conn.execute(stmt)
        self.conn.execute(
            "INSERT INTO goal_allocations(id, goal_id, date, amount_kopecks, reverses_id, created_at)"
            " SELECT id, goal_id, date, amount_kopecks, reverses_id, created_at"
            " FROM goal_allocations_pre_v8")
        self.conn.execute("DROP TABLE goal_allocations_pre_v8")
        self._mark_migration(8)

    def _migrate_steps(self) -> None:
        if self._user_version() < 1:
            self._mark_migration(1)
        if self._user_version() < 2:
            self._migrate_v2()
        if self._user_version() < 3:
            self._migrate_v3()
        if self._user_version() < 4:
            self._mark_migration(4)  # таблица budgets создана в SCHEMA (аддитивно)
        if self._user_version() < 5:
            self._migrate_v5()
        if self._user_version() < 6:
            self._migrate_v6()
        if self._user_version() < 7:
            self._migrate_v7()
        if self._user_version() < 8:
            self._migrate_v8()
        self._ensure_pending_index()

    def _ensure_pending_index(self) -> None:
        # partial-индекс очереди: колонка review_status появляется только в миграции 2,
        # поэтому индекс создаётся после миграций (идемпотентно), а не в SCHEMA.
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tx_pending ON transactions(review_status)"
            " WHERE review_status='pending'")

    def _migrate(self) -> None:
        """Версии: 1 — базовая схема; 2 — Work 3; 3 — statement_order; 4 — budgets; 5 — currency; 6 — CHECK(date); 7 — цели/копилки; 8 — предел суммы взноса (wave5 №3).

        БД новее приложения — отказ (старый код молча писал бы в незнакомую схему).
        Миграции идут в одной `BEGIN IMMEDIATE`-транзакции (DDL SQLite транзакционен): падение
        посреди апгрейда откатывает всё, а не оставляет полу-схему; второй процесс на старой БД
        ждёт блокировку и перечитывает версию внутри неё (ревью Sonnet 5.5, 30.09).
        """
        if self._user_version() > SCHEMA_VERSION:
            raise RuntimeError(
                f"БД новее приложения: schema v{self._user_version()} > v{SCHEMA_VERSION} — обновите spendtrack")
        if self._user_version() == SCHEMA_VERSION:
            self._ensure_pending_index()  # повторное открытие: только идемпотентный индекс
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self._migrate_steps()
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def _pre_migration_snapshot(self) -> None:
        """Снимок БД ПЕРЕД миграцией (VACUUM INTO — переиспользует backup.make_snapshot).

        Имя `pre-migration-*` не матчится ротацией бэкапов (`spend-*.db`) — такие снимки не удаляются.
        Сбой снимка не блокирует миграцию (она транзакционна) — предупреждение в лог
        (ревью install_ops, C1: апгрейд без пути назад запрещён).
        """
        from spendtrack.backup import make_snapshot

        try:
            snap = make_snapshot(self.path)
            # replace, не rename: на Windows rename не перезаписывает существующий файл
            # (ревью Dash 4.6) — снимок оставался под сырым именем, а target не создавался.
            snap.replace(snap.with_name(f"pre-migration-v{self._user_version()}-{snap.name}"))
        except (OSError, sqlite3.Error) as e:
            logger.warning("pre-migration snapshot failed: %s", e)

    def close(self) -> None:
        # PRAGMA optimize перед закрытием короткоживущего соединения — рекомендованная схема SQLite
        # («usually a no-op … very fast»): обновляет статистику планировщика по факту запросов.
        try:
            self.conn.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
        self.conn.close()

    # ---- account pseudonymization ----
    def pseudonymize(self, original: str | None, commit: bool = True) -> str | None:
        """Псевдоним счёта. `commit=False` — для батчей импорта (коммит делает партия, атомарность)."""
        if not original or not original.strip():
            return None
        original = original.strip()
        row = self.conn.execute("SELECT pseudonym FROM account_pseudonyms WHERE original=?", (original,)).fetchone()
        if row:
            return row["pseudonym"]
        p = "acc_" + uuid.uuid4().hex[:8]
        self.conn.execute("INSERT INTO account_pseudonyms(original, pseudonym) VALUES(?,?)", (original, p))
        if commit:
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
        currency: str | None = None,
        commit: bool = True,
    ) -> int | None:
        """Precondition: `currency` — ISO 4217 (или алиас); пусто/None → базовая валюта настроек;
        невалидный код → ValueError; дата — реальный календарный день ГГГГ-ММ-ДД (ревью wave5 S5).

        Границы (CLI/API/импорт) валидируют и нормализуют код до вызова Store.
        `commit=False` — для массовых вставок (импорт): одна транзакция на партию вместо
        commit на строку (замеры bench.py: рост скорости импорта в разы). Вызывающий **обязан**
        завершить транзакцию: `conn.commit()` при успехе и `conn.rollback()` при исключении
        (см. `import_csv`); иначе соединение остаётся с открытой транзакцией.
        """
        code = normalize_currency(currency)
        if code is None:
            if currency is None or not str(currency).strip():
                code = base_currency()  # пусто = базовая (BYN-установка не пишет RUB по умолчанию)
            else:
                raise ValueError(
                    f"Неизвестная валюта: {currency!r} (ожидается ISO 4217, например RUB/USD/EUR)")
        if not isinstance(date, str) or not _DATE_RE.fullmatch(date):
            raise ValueError("дата — формат ГГГГ-ММ-ДД")
        try:
            datetime(int(date[:4]), int(date[5:7]), int(date[8:10]), tzinfo=UTC)
        except ValueError:
            raise ValueError("дата — несуществующий день") from None
        fp = fingerprint(date, amount_kopecks, description, account_anon or "", export_rowid, code)
        existing = self.conn.execute("SELECT id FROM transactions WHERE fingerprint=?", (fp,)).fetchone()
        if existing:
            return None
        now = _now_iso()
        try:
            cur = self.conn.execute(
                "INSERT INTO transactions(date, description, amount_kopecks, currency, category, category_source,"
                " confidence, merchant, account_anon, import_batch, fingerprint, created, updated,"
                " category_llm, review_status, statement_order)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (date, description, amount_kopecks, code, category, category_source, confidence,
                 merchant, account_anon, import_batch, fp, now, now, category_llm, review_status,
                 statement_order),
            )
        except sqlite3.IntegrityError:
            # Гонка двух писателей на UNIQUE(fingerprint): победил другой — это тот же дедуп-исход
            # (ревью Sonnet 5.5, 30.09); иначе исключение с другими ограничениями не маскируем.
            if self.conn.execute("SELECT 1 FROM transactions WHERE fingerprint=?", (fp,)).fetchone():
                return None
            raise
        if commit:
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
        """Человек подтвердил предложенную категорию (или переопределил).

        P1-7 (тикет 03.10): approve и few-shot-кэш — одна транзакция; сбой кэша откатывает approve
        (раньше UPDATE коммитился до seed — крах оставлял «одобрено без кэша», повторный approve невозможен).
        """
        cur = self.conn.execute(
            "UPDATE transactions SET category=?, category_source='rule', review_status='approved',"
            " updated=? WHERE id=? AND review_status='pending'",
            (category, _now_iso(), tx_id),
        )
        if not cur.rowcount:
            self.conn.rollback()
            return False
        try:
            self._seed_merchant_cache_no_commit(tx_id)
        except BaseException:
            self.conn.rollback()
            raise
        self.conn.commit()
        return True

    def skip_review(self, tx_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE transactions SET review_status='skipped', updated=? WHERE id=? AND review_status='pending'",
            (_now_iso(), tx_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def approve_all_reviews(self, min_confidence: float = 0.0,
                            known: set[str] | None = None) -> int:
        """Одобрить очередь одной транзакцией; `min_confidence` — только записи не ниже порога.

        Безопасная пакетная работа (дизайн-ревью M-4): UI предлагает «≥ 60 %», записи с низкой
        уверенностью остаются человеку. `known` — whitelist категорий таксономии: предложение LLM
        вне таксономии не пишем (аудит 24.09: иначе doctor critical и строка без имени/цвета).
        few-shot-кэш учим только «неизвестными» мерчантами. INSERT OR IGNORE (а не upsert):
        LLM-догадка из пачки не должна перетирать ручную правку человека, уже лежащую в кэше
        (одиночный approve — осознанный выбор юзера, там upsert).
        """
        self.conn.execute("BEGIN IMMEDIATE")  # P1-5 (тикет 03.10): SELECT..UPDATE под write-lock — нет TOCTOU
        try:
            where, extra = "review_status='pending'", []
            if min_confidence > 0:
                where += " AND confidence >= ?"
                extra.append(min_confidence)
            cat_expr, known_params = "COALESCE(category_llm, category, 'other')", []
            if known:
                ph = ",".join("?" * len(known))
                cat_expr = (f"CASE WHEN category_llm IN ({ph}) THEN category_llm"
                            " ELSE COALESCE(category, 'other') END")
                known_params = sorted(known)
            rows = self.conn.execute(
                f"SELECT merchant, {cat_expr} AS cat FROM transactions WHERE {where}",
                [*known_params, *extra]).fetchall()
            now = _now_iso()
            cur = self.conn.execute(
                f"UPDATE transactions SET category={cat_expr},"
                f" category_source='rule', review_status='approved', updated=? WHERE {where}",
                [*known_params, now, *extra],
            )
            for r in rows:
                if r["merchant"]:
                    key = hashlib.sha1(r["merchant"].upper().encode()).hexdigest()
                    self.conn.execute(
                        "INSERT OR IGNORE INTO merchant_cache(key, merchant, category, updated)"
                        " VALUES(?,?,?,?)",
                        (key, r["merchant"], r["cat"], now),
                    )
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
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
            sql += " AND date >= ? AND date < ?"
            params.extend(month_bounds(month))
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
            # «крупные сверху»: по модулю суммы (доходы и расходы вместе), дата ASC, id — tie-break
            sql += " ORDER BY date ASC, ABS(amount_kopecks) DESC, id ASC LIMIT ?"
        elif sort == "amount":
            # «Крупные сначала»: по модулю суммы, свежие — при равенстве
            sql += " ORDER BY ABS(amount_kopecks) DESC, date DESC, id DESC LIMIT ?"
        else:
            # recent: внутри дня — порядок строк выписки (statement_order), иначе id
            sql += " ORDER BY date DESC, COALESCE(statement_order, id) DESC, id DESC LIMIT ?"
        params.append(str(limit))
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def export_transactions(self, month: str | None = None, category: str | None = None,
                            search: str | None = None, date_from: str | None = None,
                            date_to: str | None = None) -> tuple[dict, ...]:
        """Все транзакции периода для экспорта: read-only, без лимита страницы списка.

        Иммутабельная граница (tuple[dict]); порядок — хронологический (date ASC, id ASC).
        Материализует выборку в память: для личного трекера (десятки тысяч строк) это норма;
        стриминг под 100k+ — отдельная задача при появлении такого профиля.
        """
        sql = "SELECT * FROM transactions WHERE 1=1"
        params: list[str] = []
        if month:
            sql += " AND date >= ? AND date < ?"
            params.extend(month_bounds(month))
        if category:
            sql += " AND category=?"
            params.append(category)
        if search:
            sql += " AND (description LIKE ? OR merchant LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like])
        if date_from:
            sql += " AND date>=?"
            params.append(date_from)
        if date_to:
            sql += " AND date<=?"
            params.append(date_to)
        sql += " ORDER BY date ASC, id ASC"
        rows = self.conn.execute(sql, params).fetchall()
        return tuple(dict(r) for r in rows)

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
            where.append("date >= ? AND date < ?")
            params.extend(month_bounds(month))
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
        # Фильтры применяются и к выборке строк: дни выбраны по условию, но без этого
        # в страницу попадали ВСЕ операции этих дней (фильтр категории/поиска протекал).
        rows_clause = clause + (" AND " if clause else " WHERE ") + f"date IN ({placeholders})"
        rows = self.conn.execute(
            f"SELECT * FROM transactions{rows_clause}"
            " ORDER BY date DESC, COALESCE(statement_order, id) DESC, id DESC",
            [*params, *dates],
        ).fetchall()
        return [dict(r) for r in rows], dates[-1], has_more

    # ---- category cache by merchant ----
    def merchant_cache_get(self, merchant: str) -> str | None:
        if not merchant:
            return None
        key = hashlib.sha1(merchant.upper().encode()).hexdigest()
        row = self.conn.execute("SELECT category FROM merchant_cache WHERE key=?", (key,)).fetchone()
        return row["category"] if row else None

    def merchant_cache_set(self, merchant: str, category: str, commit: bool = True) -> None:
        """Кэш мерчанта. `commit=False` — внутри батча импорта (коммит делает партия)."""
        key = hashlib.sha1(merchant.upper().encode()).hexdigest()
        self.conn.execute(
            "INSERT INTO merchant_cache(key, merchant, category, updated) VALUES(?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET category=excluded.category, updated=excluded.updated",
            (key, merchant, category, _now_iso()),
        )
        if commit:
            self.conn.commit()

    def _seed_merchant_cache_no_commit(self, tx_id: int) -> bool:
        """few-shot-кэш для строки без собственного commit (для составных транзакций, P1-7)."""
        row = self.conn.execute(
            "SELECT merchant, category FROM transactions WHERE id=? AND merchant IS NOT NULL", (tx_id,)
        ).fetchone()
        if row and row["merchant"]:
            self.merchant_cache_set(row["merchant"], row["category"], commit=False)
            return True
        return False

    def seed_merchant_cache(self, tx_id: int) -> None:
        """Запоминает категорию по мерчанту после правки юзера (few-shot loop)."""
        if self._seed_merchant_cache_no_commit(tx_id):
            self.conn.commit()

    # ---- examples (few-shot) ----
    def add_example(self, description: str, amount_kopecks: int, category: str) -> None:
        self.conn.execute("INSERT INTO examples(description, amount_kopecks, category) VALUES(?,?,?)",
                          (description, amount_kopecks, category))
        self.conn.commit()

    def list_examples(self, limit: int = 8) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM examples ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---- бюджеты по категориям ----
    def set_budget(self, category: str, amount_kopecks: int) -> None:
        if amount_kopecks <= 0:
            raise ValueError("бюджет должен быть больше нуля")
        self.conn.execute(
            "INSERT INTO budgets(category, amount_kopecks, updated) VALUES(?,?,?)"
            " ON CONFLICT(category) DO UPDATE SET amount_kopecks=excluded.amount_kopecks,"
            " updated=excluded.updated",
            (category, int(amount_kopecks), _now_iso()),
        )
        self.conn.commit()

    def clear_budget(self, category: str) -> None:
        self.conn.execute("DELETE FROM budgets WHERE category=?", (category,))
        self.conn.commit()

    def budget_map(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT category, amount_kopecks FROM budgets").fetchall()
        return {r["category"]: r["amount_kopecks"] for r in rows}

    # ---- цели/копилки (v7, research 03.10) ----
    def add_goal(self, title: str, target_kopecks: int, currency: str | None = None,
                 due_month: str | None = None) -> int:
        """Создать цель («виртуальный конверт»). Валидация здесь; SQL CHECK — второй рубеж."""
        t = (title or "").strip()
        if not 1 <= len(t) <= 120:
            raise ValueError("название цели: от 1 до 120 символов")
        if not isinstance(target_kopecks, int) or not 0 < target_kopecks <= MAX_AMOUNT_KOPECKS:
            raise ValueError("сумма цели — целое число копеек > 0 и в пределах лимита")
        code = (currency or base_currency()).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("валюта цели — код ISO 4217 (3 латинские буквы)")
        if due_month is not None and not valid_month(due_month):
            raise ValueError("срок цели — формат ГГГГ-ММ (или пусто)")
        now = _now_iso()
        month = _date_cls.today().strftime("%Y-%m")  # noqa: DTZ011 — локальный месяц намеренно (BYN UTC+3)
        cur = self.conn.execute(
            "INSERT INTO goals(title, target_kopecks, currency, due_month, created_month,"
            " archived, created, updated) VALUES(?,?,?,?,?,0,?,?)",
            (t, int(target_kopecks), code, due_month, month, now, now))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_goals(self, include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM goals"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def archive_goal(self, goal_id: int, archived: bool = True) -> bool:
        """Архив вместо удаления: взносы — история (FK ON DELETE RESTRICT). False — цели нет."""
        cur = self.conn.execute("UPDATE goals SET archived=?, updated=? WHERE id=?",
                                (1 if archived else 0, _now_iso(), int(goal_id)))
        self.conn.commit()
        return cur.rowcount > 0

    def add_allocation(self, goal_id: int, date: str, amount_kopecks: int) -> int:
        """Взнос (>0) или изъятие (<0) — append-only; дата не в будущем (локальная), цель не в архиве.

        Проверка `archived` и INSERT — в одной `BEGIN IMMEDIATE`-транзакции (ревью wave5, S7: TOCTOU).
        """
        if not isinstance(date, str) or not _DATE_RE.fullmatch(date):
            raise ValueError("дата взноса — формат ГГГГ-ММ-ДД")
        try:
            d = datetime(int(date[:4]), int(date[5:7]), int(date[8:10]), tzinfo=UTC).date()
        except ValueError:
            raise ValueError("дата взноса — несуществующий день") from None
        if d > _date_cls.today():  # noqa: DTZ011 — локальная дата намеренно (BYN-установки UTC+3)
            raise ValueError("дата взноса — не в будущем")
        # wave5 №3: предел как у целей — иначе SUM(INTEGER) переполнялся и давал ложный 503
        if (not isinstance(amount_kopecks, int)
                or not 0 < abs(amount_kopecks) <= MAX_AMOUNT_KOPECKS):
            raise ValueError("сумма взноса — целое число копеек ≠ 0 и в пределах лимита")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            goal = self.conn.execute("SELECT archived FROM goals WHERE id=?",
                                     (int(goal_id),)).fetchone()
            if goal is None:
                raise ValueError(f"цель {goal_id} не найдена")
            if goal["archived"]:
                raise ValueError("цель в архиве — взносы невозможны")
            cur = self.conn.execute(
                "INSERT INTO goal_allocations(goal_id, date, amount_kopecks, created_at)"
                " VALUES(?,?,?,?)", (int(goal_id), date, int(amount_kopecks), _now_iso()))
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return int(cur.lastrowid)

    def list_allocations(self, goal_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM goal_allocations WHERE goal_id=? ORDER BY date, id",
            (int(goal_id),)).fetchall()
        return [dict(r) for r in rows]

    def goal_progress(self, goal_id: int) -> dict:
        """Прогресс считается на лету (derived не храним) — подписанная сумма взносов."""
        goal = self.conn.execute("SELECT * FROM goals WHERE id=?", (int(goal_id),)).fetchone()
        if goal is None:
            raise ValueError(f"цель {goal_id} не найдена")
        agg = self.conn.execute(
            "SELECT COALESCE(SUM(amount_kopecks), 0) AS s, COUNT(*) AS n"
            " FROM goal_allocations WHERE goal_id=?", (int(goal_id),)).fetchone()
        allocated, target = int(agg["s"]), int(goal["target_kopecks"])
        return {
            "goal_id": int(goal_id),
            "title": goal["title"],
            "currency": goal["currency"],
            "target_kopecks": target,
            "allocated_kopecks": allocated,
            "remaining_kopecks": max(0, target - allocated),
            "allocations": int(agg["n"]),
            "done": allocated >= target,
        }

    # ---- import batches ----
    def add_batch(self, filename: str, sha: str, nrows: int, commit: bool = True) -> str:
        """Партия импорта; `commit=False` — в общей транзакции импорта (аудит 24.09:
        иначе запись партии переживала rollback и копилась пустыми партиями)."""
        batch_id = "b_" + uuid.uuid4().hex[:10]
        self.conn.execute(
            "INSERT INTO import_batches(id, filename, sha, nrows, created) VALUES(?,?,?,?,?)",
            (batch_id, filename, sha, nrows, _now_iso()),
        )
        if commit:
            self.conn.commit()
        return batch_id

    def counts(self) -> dict:
        rows = self.conn.execute(
            "SELECT category_source, COUNT(*) c FROM transactions GROUP BY category_source"
        ).fetchall()
        return {r["category_source"]: r["c"] for r in rows}

    def has_transactions(self) -> bool:
        """Быстрая проверка «есть ли данные» для страниц: EXISTS вместо GROUP BY (замеры bench.py)."""
        return bool(self.conn.execute("SELECT EXISTS(SELECT 1 FROM transactions)").fetchone()[0])

    def batch_count(self) -> int:
        """Число партий импорта (read-only; для онбординга «первый запуск»)."""
        return int(self.conn.execute("SELECT COUNT(*) c FROM import_batches").fetchone()["c"])