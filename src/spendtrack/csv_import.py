from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from io import StringIO

from spendtrack.categorize import categorize_transaction
from spendtrack.store import Store, parse_amount
from spendtrack.taxonomy import Taxonomy


def _cell(row: dict, *keys: str) -> str:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k]).strip()
    return ""


def _guess_sep(header: str) -> str:
    return ";" if header.count(";") >= header.count(",") else ","


class SberAdaptor:
    """Sber export.csv: Тип операции, Дата, Номер карты, Статус, Сумма операции, Валюта операции, Описание."""

    def parse(self, rows: Iterator[dict]) -> Iterator[dict]:
        for r in rows:
            date = _cell(r, "Дата операции", "Дата")
            desc = _cell(r, "Описание", "Категория")
            amount = _cell(r, "Сумма операции", "Сумма")
            account = _cell(r, "Номер карты")
            if not date or not desc or not amount:
                continue
            yield {"date": date[:10], "description": desc, "amount_kopecks": parse_amount(amount),
                   "account": account or None, "export_rowid": ""}


class TinkoffAdaptor:
    """Tinkoff export: Дата, Сумма операции, Категория, Описание, Счёт."""

    def parse(self, rows: Iterator[dict]) -> Iterator[dict]:
        for r in rows:
            date = _cell(r, "Дата", "Date")
            desc = _cell(r, "Описание", "Description")
            amount = _cell(r, "Сумма операции", "Сумма", "Amount")
            account = _cell(r, "Счёт", "Account")
            if not date or not desc or not amount:
                continue
            yield {"date": date[:10], "description": desc, "amount_kopecks": parse_amount(amount),
                   "account": account or None, "export_rowid": ""}


class YandexMoneyAdaptor:
    """Yandex: datetime, operation, amount, currency, category, title, merchant, description."""

    def parse(self, rows: Iterator[dict]) -> Iterator[dict]:
        for r in rows:
            date = _cell(r, "datetime", "date", "Дата")
            desc = _cell(r, "description", "title", "Описание")
            amount = _cell(r, "amount", "Сумма")
            account = _cell(r, "account", "Счёт")
            if not date or not desc or not amount:
                continue
            yield {"date": date[:10], "description": desc, "amount_kopecks": parse_amount(amount),
                   "account": account or None, "export_rowid": ""}


BANKS = {
    "sber": SberAdaptor(),
    "tinkoff": TinkoffAdaptor(),
    "yandex": YandexMoneyAdaptor(),
    "auto": None,  # снеффинг по колонкам
}


def sniff_bank(rows: list[dict]) -> str | None:
    if not rows:
        return None
    keys = set(rows[0].keys())
    if "Дата операции" in keys:
        return "sber"
    if "Счёт" in keys or ("Сумма операции" in keys and "Описание" in keys):
        return "tinkoff"
    if "datetime" in keys:
        return "yandex"
    return None


def import_csv(
    raw: str | bytes,
    store: Store,
    bank: str = "auto",
    taxonomy: Taxonomy | None = None,
    classify=None,
) -> dict:
    """Импорт CSV. classify — инжектируемый (tx, store, taxonomy) -> dict с категоризацией.
    По умолчанию — боевой categorize_transaction (может ходить в LLM)."""
    if taxonomy is None:
        from spendtrack.config import ROOT
        from spendtrack.taxonomy import load_taxonomy
        taxonomy = load_taxonomy(ROOT / "config")
    if classify is None:
        classify = lambda tx, st, tax: categorize_transaction(tx, tax, st)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig", errors="replace")
    raw = raw.lstrip("\ufeff")

    lines = raw.splitlines()
    if not lines:
        return {"status": "empty", "added": 0, "dupes": 0, "rows": 0}

    reader_all = [dict(r) for r in csv.DictReader(StringIO(raw), delimiter=_guess_sep(lines[0]))]
    if not reader_all:
        return {"status": "empty", "added": 0, "dupes": 0, "rows": 0}

    bank_name = bank
    if bank_name == "auto":
        sniffed = sniff_bank(reader_all)
        bank_name = sniffed or "sber"
    adaptor = BANKS[bank_name]

    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    batch_id = store.add_batch("unknown.csv", sha, len(reader_all))

    added, dupes = 0, 0
    for rownum, tx in enumerate(adaptor.parse(iter(reader_all))):
        tx["export_rowid"] = str(rownum)
        account_anon = store.pseudonymize(tx.pop("account", None))
        tx["account_anon"] = account_anon
        classification = classify(tx, store, taxonomy)
        tx["category"] = classification["category"]
        tx["category_source"] = classification["source"]
        tx["confidence"] = classification["confidence"]
        tx["merchant"] = classification["merchant"] or None
        if store.add_transaction(import_batch=batch_id, **tx):
            added += 1
        else:
            dupes += 1

    return {"status": "ok", "bank": bank_name, "added": added, "dupes": dupes, "rows": len(reader_all)}