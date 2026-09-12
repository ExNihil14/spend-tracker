from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from spendtrack.categorize import categorize_transaction
from spendtrack.csv_import import import_csv
from spendtrack.store import Store, parse_amount
from spendtrack.taxonomy import load_taxonomy

router = APIRouter()


def _store() -> Store:
    return Store()


class TxIn(BaseModel):
    date: str
    description: str
    amount: str
    account: str | None = None


class ConfirmIn(BaseModel):
    category: str


class ImportIn(BaseModel):
    bank: str = "auto"
    csv: str


@router.post("/transactions")
def create(tx: TxIn):
    store = _store()
    taxonomy = load_taxonomy()
    amount = parse_amount(tx.amount)
    account_anon = store.pseudonymize(tx.account)
    category = categorize_transaction(
        {"date": tx.date, "description": tx.description, "amount_kopecks": amount,
         "merchant": tx.description.upper()[:20], "account_anon": account_anon},
        taxonomy, store,
    )
    tx_id = store.add_transaction(
        date=tx.date, description=tx.description, amount_kopecks=amount,
        category=category["category"], category_source=category["source"],
        confidence=category["confidence"], merchant=category["merchant"],
        account_anon=account_anon, export_rowid="",
    )
    return {"id": tx_id, **category}


@router.patch("/transactions/{tx_id}")
def confirm(tx_id: int, body: ConfirmIn):
    store = _store()
    taxonomy = load_taxonomy()
    if not taxonomy.is_valid(body.category):
        raise HTTPException(422, f"категория {body.category} вне таксономии")
    ok = store.update_category(tx_id, body.category, source="correction")
    store.seed_merchant_cache(tx_id)
    if not ok:
        raise HTTPException(404, "не найдено")
    return {"ok": True}


@router.get("/transactions/{tx_id}")
def get_one(tx_id: int):
    store = _store()
    tx = store.get_transaction(tx_id)
    if not tx:
        raise HTTPException(404, "не найдено")
    return tx


@router.post("/import")
def do_import(body: ImportIn):
    store = _store()
    taxonomy = load_taxonomy()
    result = import_csv(body.csv, store, bank=body.bank, taxonomy=taxonomy)
    return result