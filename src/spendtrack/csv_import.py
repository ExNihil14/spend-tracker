from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterator
from decimal import InvalidOperation
from io import StringIO

from spendtrack.categorize import categorize_transaction
from spendtrack.store import Store, fingerprint, normalize_currency, parse_amount
from spendtrack.taxonomy import Taxonomy

_DATE_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_DATE_DDMMYYYY = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})")

MAX_CSV_BYTES = 10 * 1024 * 1024          # 10 МБ: даже многолетняя выписка меньше; защита от OOM
MAX_AMOUNT_KOPECKS = 100_000_000_000      # 1 млрд руб на операцию — санитарный предел (защита от мусорных строк)

# Дрейф формата (POLISH_PLAN P1 #1): вместо тихого мисс-парсинга — отчёт `format_error`
# с недостающими колонками и просьбой прислать обезличенный образец (scripts/anonymize.py).
FORMAT_HINT = (
    "Похоже, банк изменил формат выписки. Пришлите, пожалуйста, обезличенный образец "
    "(первые строки; обезличить: `python scripts/anonymize.py файл.csv`) в issue — "
    "https://github.com/ExNihil14/spend-tracker/issues/new"
)

# Логические поля → колонки-синонимы: хотя бы одна должна найтись (стирание пробелов/регистра — норма).
REQUIRED_COLUMNS: dict[str, tuple[tuple[str, ...], ...]] = {
    # Реальные шапки подтверждены публичными первоисточниками (RESEARCH_BANK_STATEMENT_SAMPLES.md):
    # Сбер email-CSV: «Тип карты;Номер карты;Дата совершения операции;…;Сумма в валюте счета»;
    # Т-Банк: «Дата операции;Дата платежа;…;Статус;…;MCC;Описание;Бонусы» (13 колонок).
    "sber": (("Дата совершения операции", "Дата операции", "Дата"), ("Описание", "Категория"),
             ("Сумма в валюте счета", "Сумма в валюте операции", "Сумма операции", "Сумма")),
    "tinkoff": (("Дата операции", "Дата", "Date"), ("Описание", "Description"),
                ("Сумма операции", "Сумма", "Amount")),
    "yandex": (("datetime", "date", "Дата"), ("description", "title", "Описание"), ("amount", "Сумма")),
}

# Отчёт импорта (#2): пропущено (с причинами) и подозрительно (импортировано, но с признаками).
SKIP_REASONS = ("duplicate", "status", "missing_fields", "amount_unparsed", "amount_limit")
SUSPICIOUS_REASONS = ("date_unrecognized",)
REASON_LABELS = {
    "duplicate": "дубли",
    "status": "не проведены банком",
    "missing_fields": "пустые обязательные поля",
    "amount_unparsed": "не разобрана сумма",
    "amount_limit": "сумма сверх лимита",
}
SUSPICIOUS_LABELS = {"date_unrecognized": "нераспознанная дата"}


class ImportLimitError(ValueError):
    """Превышен лимит импорта (размер и т.п.) — API отдаёт 413, CLI код 1, остальное 500/баг."""


def _cell(row: dict, *keys: str) -> str:
    """Значение по синонимам колонок (приоритет — порядок аргументов).

    Пробелы/регистр в заголовках не ломают поиск: банк может добавить « » или сменить регистр.
    """
    by_norm: dict[str, object] = {}
    for key, value in row.items():
        if key:
            by_norm.setdefault(key.strip().lower(), value)
    for k in keys:
        value = by_norm.get(k.strip().lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _iso_date(value: str) -> str:
    """DD.MM.YYYY[ HH:MM] → YYYY-MM-DD (месячные фильтры/сортировка/дашборд — на ISO)."""
    v = value.strip()
    m = _DATE_ISO.match(v)
    if m:
        return m.group(1)
    m = _DATE_DDMMYYYY.match(v)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return v[:10]


def _date_recognized(value: str) -> bool:
    v = value.strip()
    return bool(_DATE_ISO.match(v) or _DATE_DDMMYYYY.match(v))


def _guess_sep(header: str) -> str:
    return ";" if header.count(";") >= header.count(",") else ","


def missing_columns(bank: str, fieldnames: list[str]) -> list[str]:
    """Логические поля банка, для которых в файле нет ни одной колонки-синонима.

    Возвращает группу синонимов через « / » (у банка бывает несколько форматов: email-CSV Сбера
    и старый экспорт) — пользователю видно, какие названия колонок мы искали.
    """
    names = {f.strip().lower() for f in fieldnames if f}
    return [" / ".join(group) for group in REQUIRED_COLUMNS.get(bank, ())
            if not any(alias.lower() in names for alias in group)]


def _row_tx(date: str, desc: str, amount: str, account: str, currency: str = "") -> dict:
    """Строка выписки → tx или маркер пропуска `_skip` (общая сборка для всех адаптеров).

    Непарсящаяся сумма/пустые обязательные поля не роняют импорт и не теряются молча —
    попадают в отчёт причинами. Нераспознанная дата импортируется с пометкой `_suspicious`.
    Незнакомая валюта трактуется как RUB (базовая): импорт не должен падать из-за неё.
    """
    if not date or not desc or not amount:
        return {"_skip": "missing_fields"}
    try:
        kopecks = parse_amount(amount)
    except (InvalidOperation, ValueError, OverflowError):
        return {"_skip": "amount_unparsed"}
    tx = {"date": _iso_date(date), "description": desc, "amount_kopecks": kopecks,
          "account": account or None, "export_rowid": "",
          "currency": normalize_currency(currency) or "RUB"}
    if not _date_recognized(date):
        tx["_suspicious"] = "date_unrecognized"
    return tx


class SberAdaptor:
    """Sber: export.csv и email-CSV («выписка на e-mail как Excel-лист», реальная шапка подтверждена).

    Email-CSV: `Тип карты;Номер карты;Дата совершения операции;…;Описание;Валюта операции;
    Сумма в валюте операции;Сумма в валюте счета`. Статуса в нём нет; расчётная сумма — «в валюте счёта»
    (у физлиц РФ счёт рублёвый), поэтому берём её с валютой RUB; иначе — сумму/валюту операции.
    """

    def parse(self, rows: Iterator[dict]) -> Iterator[dict]:
        for r in rows:
            status = _cell(r, "Статус", "Status").lower()
            if status in ("в обработке", "отклонено", "отменено", "ошибка"):
                yield {"_skip": "status"}
                continue
            account_sum = _cell(r, "Сумма в валюте счета")
            if account_sum:
                amount, currency = account_sum, "RUB"
            else:
                amount = _cell(r, "Сумма в валюте операции", "Сумма операции", "Сумма")
                currency = _cell(r, "Валюта операции", "Валюта")
            yield _row_tx(_cell(r, "Дата совершения операции", "Дата операции", "Дата"),
                          _cell(r, "Описание", "Категория"), amount,
                          _cell(r, "Номер карты"), currency)


class TinkoffAdaptor:
    """T-Bank (Тинькофф): реальная шапка 13 колонок (`Дата операции;…;Статус;…;MCC;Описание;Бонусы`)
    и старый простой экспорт (`Дата;Сумма операции;Категория;Описание;Счёт`). Проведённые — `Статус=OK`.
    """

    def parse(self, rows: Iterator[dict]) -> Iterator[dict]:
        for r in rows:
            status = _cell(r, "Статус", "Status")
            if status and status.lower() != "ok":
                yield {"_skip": "status"}
                continue
            yield _row_tx(_cell(r, "Дата операции", "Дата", "Date"),
                          _cell(r, "Описание", "Description"),
                          _cell(r, "Сумма операции", "Сумма", "Amount"),
                          _cell(r, "Номер карты", "Счёт", "Account"),
                          _cell(r, "Валюта операции", "Валюта", "Currency"))


class YandexMoneyAdaptor:
    """Yandex: datetime, operation, amount, currency, category, title, merchant, description."""

    def parse(self, rows: Iterator[dict]) -> Iterator[dict]:
        for r in rows:
            yield _row_tx(_cell(r, "datetime", "date", "Дата"),
                          _cell(r, "description", "title", "Описание"),
                          _cell(r, "amount", "Сумма"), _cell(r, "account", "Счёт"),
                          _cell(r, "currency", "Валюта"))


BANKS = {
    "sber": SberAdaptor(),
    "tinkoff": TinkoffAdaptor(),
    "yandex": YandexMoneyAdaptor(),
    "auto": None,  # снеффинг по колонкам
}


def sniff_bank(rows: list[dict]) -> str | None:
    if not rows:
        return None
    keys = {k.strip().lower() for k in rows[0] if k}
    # Реальный Т-Банк (13 колонок) тоже содержит «Дата операции» — его выдают MCC/кэшбэк/бонусы;
    # проверяем их раньше Сбера, иначе реальная выписка Т-Банка опознавалась как Сбер.
    if "mcc" in keys or "кэшбэк" in keys or "бонусы (включая кэшбэк)" in keys:
        return "tinkoff"
    # Сбер: «Дата совершения операции» (email-CSV), «Дата операции»/«Дата платежа» — устойчивые маркеры.
    if "дата совершения операции" in keys or "дата операции" in keys or "дата платежа" in keys:
        return "sber"
    if "счёт" in keys or ("сумма операции" in keys and "описание" in keys):
        return "tinkoff"
    if "datetime" in keys:
        return "yandex"
    return None


def _empty_result(rows: int = 0) -> dict:
    return {"status": "empty", "added": 0, "dupes": 0, "invalid": 0,
            "skipped": 0, "suspicious": 0, "reasons": {}, "suspicious_reasons": {}, "rows": rows}


def _format_error(bank: str | None, fieldnames: list[str], rows: int, message: str,
                  missing: list[str] | None = None) -> dict:
    """Отчёт о дрейфе формата: данные не менялись, пользователю — причина и следующий шаг."""
    return {"status": "format_error", "bank": bank, "added": 0, "dupes": 0, "invalid": 0,
            "skipped": rows, "suspicious": 0, "reasons": {}, "suspicious_reasons": {},
            "missing_columns": missing or [], "found_columns": fieldnames,
            "rows": rows, "message": message}


def import_csv(
    raw: str | bytes,
    store: Store,
    bank: str = "auto",
    taxonomy: Taxonomy | None = None,
    classify=None,
    filename: str = "unknown.csv",
) -> dict:
    """Импорт CSV. classify — инжектируемый (tx, store, taxonomy) -> dict с категоризацией.
    По умолчанию — боевой categorize_transaction с commit=False (партия атомарна: ни строки,
    ни псевдонимы счетов, ни кэш мерчанта не коммитятся посередине; rollback при сбое — здесь же).
    Кастомный classify, если пишет в БД, обязан сам использовать commit=False.
    `filename` — имя источника для партии (CLI передаёт реальное имя файла)."""
    raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    if len(raw_bytes) > MAX_CSV_BYTES:  # лимит в БАЙТАХ (кириллица = 2 байта/символ), проверка первой
        raise ImportLimitError(
            f"CSV превышает лимит {MAX_CSV_BYTES // (1024 * 1024)} МБ ({len(raw_bytes)} байт) — "
            "разделите выписку по периодам")
    if taxonomy is None:
        from spendtrack.taxonomy import load_taxonomy
        taxonomy = load_taxonomy()
    if classify is None:
        # commit=False: кэш мерчанта пишется в транзакции партии (атомарность импорта)
        classify = lambda tx, st, tax: categorize_transaction(tx, tax, st, commit=False)
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw = raw.decode("cp1251", errors="replace")
    raw = raw.lstrip("\ufeff")

    lines = raw.splitlines()
    if not lines:
        return _empty_result()

    reader = csv.DictReader(StringIO(raw), delimiter=_guess_sep(lines[0]))
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    reader_all = [dict(r) for r in reader]
    if not reader_all:
        return _empty_result()

    bank_name = bank
    if bank_name == "auto":
        sniffed = sniff_bank(reader_all)
        if sniffed is None or missing_columns(sniffed, fieldnames):
            # колонки могли частично переименовать — пробуем остальные банки по обязательным полям
            candidates = [name for name in ("sber", "tinkoff", "yandex")
                          if not missing_columns(name, fieldnames)]
            if candidates and (len(candidates) == 1 or sniffed is None):
                # несколько банков подходят под обязательные колонки (например, без уникальных
                # маркеров) — дрейфа нет, берём первый по историческому приоритету (sber)
                sniffed = candidates[0]
        if sniffed is None:
            return _format_error(None, fieldnames, len(reader_all),
                                 message="Не удалось определить банк по колонкам. " + FORMAT_HINT)
        bank_name = sniffed
    adaptor = BANKS.get(bank_name)
    if adaptor is None:
        return _format_error(bank_name, fieldnames, len(reader_all),
                             message=f"Неизвестный банк: {bank_name!r} (доступны: sber, tinkoff, yandex).")
    missing = missing_columns(bank_name, fieldnames)
    if missing:
        return _format_error(bank_name, fieldnames, len(reader_all), missing=missing,
                             message=(f"В файле нет ожидаемых колонок ({bank_name}): "
                                      + ", ".join(missing) + ". " + FORMAT_HINT))

    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    batch_id = store.add_batch(filename, sha, len(reader_all))

    added = 0
    seq = 0
    seen: dict[str, int] = {}
    reasons = dict.fromkeys(SKIP_REASONS, 0)
    suspicious = dict.fromkeys(SUSPICIOUS_REASONS, 0)
    try:
        for tx in adaptor.parse(iter(reader_all)):
            if "_skip" in tx:
                reasons[tx["_skip"]] += 1
                continue
            if abs(tx["amount_kopecks"]) > MAX_AMOUNT_KOPECKS:
                reasons["amount_limit"] += 1  # мусорная строка (битый экспорт) — в отчёт, не в БД
                continue
            mark = tx.pop("_suspicious", None)
            if mark:
                suspicious[mark] += 1
            tx["statement_order"] = seq
            seq += 1
            account_anon = store.pseudonymize(tx.pop("account", None), commit=False)
            tx["account_anon"] = account_anon
            # export_rowid = индекс ПОВТОРЯЕМОСТИ (0,1,2...) одинаковых операций, а не позиция строки:
            # реэкспорт со сдвигом строк не создаёт дублей, а легитимные одинаковые покупки в один
            # день различаются (fable-review 12.09 + фикс сдвига реэкспорта 15.09).
            base = fingerprint(tx["date"], tx["amount_kopecks"], tx["description"], account_anon or "", "",
                               tx.get("currency", "RUB"))
            tx["export_rowid"] = str(seen.get(base, 0))
            seen[base] = seen.get(base, 0) + 1
            classification = classify(tx, store, taxonomy)
            tx["category"] = classification["category"]
            tx["category_source"] = classification["source"]
            tx["confidence"] = classification["confidence"]
            tx["merchant"] = classification["merchant"] or None
            # Низкая уверенность LLM → очередь подтверждения (иначе все импортные строки «approved»
            # и категория-предложение LLM терялись — найден офлайн-тестом, 19.09).
            tx["review_status"] = classification.get("review_status", "approved")
            tx["category_llm"] = classification.get("category_llm")
            if store.add_transaction(commit=False, import_batch=batch_id, **tx):
                added += 1
            else:
                reasons["duplicate"] += 1
    except Exception:
        # Партия атомарна: сбой в середине не оставляет половину строк и не держит транзакцию открытой.
        store.conn.rollback()
        raise
    store.conn.commit()  # одна транзакция на партию, а не commit на строку (замеры bench.py)

    return {"status": "ok", "bank": bank_name, "added": added,
            "dupes": reasons["duplicate"], "invalid": reasons["amount_limit"],
            "skipped": sum(reasons.values()), "suspicious": sum(suspicious.values()),
            "reasons": {k: v for k, v in reasons.items() if v},
            "suspicious_reasons": {k: v for k, v in suspicious.items() if v},
            "rows": len(reader_all)}


def summarize(result: dict) -> str:
    """Человекочитаемый отчёт импорта — единый текст для CLI и UI (#2 POLISH_PLAN)."""
    status = result.get("status")
    if status == "format_error":
        return str(result.get("message", "Ошибка формата выписки"))
    if status == "empty":
        return "Пустой файл"
    parts = [f"+{result.get('added', 0)} добавлено"]
    reasons = result.get("reasons") or {}
    if result.get("skipped"):
        detail = ", ".join(f"{REASON_LABELS.get(k, k)}: {v}" for k, v in reasons.items())
        parts.append(f"{result['skipped']} пропущено" + (f" ({detail})" if detail else ""))
    suspicious = result.get("suspicious_reasons") or {}
    if result.get("suspicious"):
        detail = ", ".join(f"{SUSPICIOUS_LABELS.get(k, k)}: {v}" for k, v in suspicious.items())
        parts.append(f"{result['suspicious']} подозрительно" + (f" ({detail})" if detail else ""))
    if result.get("bank"):
        parts.append(f"банк={result['bank']}")
    return " · ".join(parts)
