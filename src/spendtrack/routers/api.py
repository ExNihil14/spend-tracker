from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError, field_validator

from spendtrack.assets import static_url
from spendtrack.categorize import categorize_transaction
from spendtrack.colors import badge_text_color
from spendtrack.config import PKG_DIR
from spendtrack.csv_import import MAX_CSV_BYTES, ImportLimitError, import_csv, summarize
from spendtrack.deps import get_store
from spendtrack.reports import budgets_progress
from spendtrack.store import (
    Store,
    fmt_amount,
    fmt_date,
    fmt_money,
    fmt_month,
    normalize_currency,
    parse_amount,
)
from spendtrack.taxonomy import load_taxonomy

router = APIRouter()
templates = Jinja2Templates(directory=PKG_DIR / "templates")
templates.env.globals.update(
    fmt_money=fmt_money, fmt_month=fmt_month, fmt_date=fmt_date,
    badge_text=badge_text_color, static=static_url,
)


class TxIn(BaseModel):
    date: str
    description: str
    amount: str
    account: str | None = None
    currency: str = "RUB"

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str) -> str:
        code = normalize_currency(value)
        if code is None:
            raise ValueError("Неизвестная валюта (ожидается код ISO 4217, например RUB/USD/EUR)")
        return code


class ConfirmIn(BaseModel):
    category: str


class ImportIn(BaseModel):
    bank: str = "auto"
    csv: str


def _validation_422(exc: ValidationError) -> HTTPException:
    """422 с безопасными ctx (объект исключения кастомного валидатора не сериализуется → 500)."""
    errors = [
        {**err, "ctx": {k: str(v) for k, v in err["ctx"].items()}}
        if isinstance(err.get("ctx"), dict) else err
        for err in exc.errors()
    ]
    return HTTPException(422, detail=errors)


async def _json_payload[T: BaseModel](request: Request, model: type[T]) -> T:
    """Разбор JSON-тела: битая кодировка → 400, неверные поля → 422 (а не 500 на ровном месте)."""
    try:
        data = await request.json()
    except ValueError as e:  # JSONDecodeError/UnicodeDecodeError — тело не UTF-8/не JSON
        raise HTTPException(400, detail="Тело запроса — некорректный JSON (ожидается UTF-8)") from e
    try:
        return model(**data)
    except ValidationError as e:
        raise _validation_422(e) from e


@router.post("/transactions")
async def create(request: Request, store: Annotated[Store, Depends(get_store)]):
    taxonomy = load_taxonomy()
    ct = request.headers.get("content-type", "application/json")
    if "application/json" in ct:
        tx = await _json_payload(request, TxIn)
    else:
        form = await request.form()
        payload = {k: str(v) for k, v in
                   ((k, form.get(k)) for k in ("date", "description", "amount", "account", "currency"))
                   if v is not None}
        try:
            tx = TxIn(**payload)
        except ValidationError as e:  # форма без обязательного поля → 422 (как JSON), а не 500
            raise _validation_422(e) from e
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
        category_llm=category.get("category_llm"),
        review_status=category.get("review_status", "approved"),
        currency=tx.currency,
    )
    if request.headers.get("hx-request", "").lower() == "true":
        label = category["category"]
        if category["source"] == "llm_pending_review":
            msg = (f"Добавлено: {tx.description} → <b>{label}</b> "
                   f"(conf {category['confidence']:.2f}), ждёт подтверждения.")
        else:
            msg = f"Добавлено: {tx.description} → <b>{label}</b>"
        return HTMLResponse(f'<p class="text-blue-400">{msg}</p>')
    return {"id": tx_id, **category}


@router.get("/budgets")
def budgets(store: Annotated[Store, Depends(get_store)], month: str | None = None):
    """Прогресс по бюджетам за месяц (по умолчанию — месяц последней транзакции)."""
    taxonomy = load_taxonomy()
    if not month:
        row = store.conn.execute("SELECT MAX(date) m FROM transactions").fetchone()
        month = (row["m"] or datetime.now(UTC).strftime("%Y-%m-%d"))[:7]
    items = budgets_progress(store, month, known={c.name for c in taxonomy.categories})
    return {"month": month, "items": items}


@router.get("/pending-count")
def pending_count(store: Annotated[Store, Depends(get_store)]):
    return {"count": store.pending_count()}


@router.get("/reviews", response_class=HTMLResponse)
def list_reviews(request: Request, store: Annotated[Store, Depends(get_store)]):
    """htmx-фрагмент очереди (одно место рендера → страница и oob едины)."""
    return HTMLResponse(_rows_html(request, store))


@router.get("/reviews/count", response_class=HTMLResponse)
def reviews_count(request: Request, store: Annotated[Store, Depends(get_store)]):
    n = store.pending_count()
    body = (
        '<span id="pending-count" hx-swap-oob="true"'
        ' class="ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-500/20 text-amber-300">'
        f"{n}</span>"
    )
    return HTMLResponse(body)


def _oob_badge(store: Store) -> str:
    n = store.pending_count()
    return (
        '<span id="pending-count" hx-swap-oob="true"'
        ' class="ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-500/20 text-amber-300">'
        f"{n}</span>"
    )


def _rows_html(request: Request, store: Store) -> str:
    """Единый рендер фрагмента очереди (страница и htmx-ответы совпадают)."""
    taxonomy = load_taxonomy()
    cats = {c.name: c.color for c in taxonomy.categories}
    return templates.TemplateResponse(
        request, "partials/review_rows.html",
        {"pending": store.queued_for_review(), "cat_colors": cats, "fmt": fmt_amount,
         "catname": taxonomy.display,
         "all_categories": [c.name for c in taxonomy.categories]},
    ).body.decode()


def _oob_approve_all(request: Request, store: Store) -> str:
    """OOB: кнопка «Одобрить все» живёт/исчезает вместе с очередью."""
    return templates.TemplateResponse(
        request, "partials/approve_all.html",
        {"pending": store.queued_for_review(), "oob": True},
    ).body.decode()


def _oob_empty_state(request: Request, store: Store) -> str:
    """OOB: плейсхолдер «Все подтверждены» появляется/убирается без перерисовки таблицы.

    Разметка — общий partial `partials/review_empty.html` (тот же, что в `review_rows.html`):
    единый вид пустой очереди и при OOB-добавлении после последнего решения.
    """
    if store.pending_count() == 0:
        return templates.TemplateResponse(
            request, "partials/review_empty.html", {"oob": True}).body.decode()
    return '<tr id="review-empty" hx-swap-oob="delete"></tr>'


def _oob_toast(text: str) -> str:
    """OOB-тост с подтверждением действия (aria-live; авто-скрытие — скрипт в base.html)."""
    return (
        '<div id="toast" hx-swap-oob="outerHTML" data-flash="1" role="status" aria-live="polite"'
        ' class="fixed bottom-4 right-4 z-50 transition-opacity duration-200 bg-slate-800'
        ' border border-slate-600 text-slate-100 text-sm rounded-lg px-4 py-2 shadow-xl">'
        f"{escape(text)}</div>"
    )


@router.post("/reviews/{tx_id}/approve", response_class=HTMLResponse)
async def approve_review(request: Request, tx_id: int, store: Annotated[Store, Depends(get_store)]):
    taxonomy = load_taxonomy()
    proposal = store.get_transaction(tx_id)
    if not proposal:
        raise HTTPException(404, "не найдено")
    form = await request.form()
    chosen = str(form.get("category") or "") or proposal.get("category_llm") or proposal.get("category")
    if not taxonomy.is_valid(str(chosen)):
        raise HTTPException(422, f"категория {chosen} вне таксономии")
    if not store.approve_review(tx_id, str(chosen)):
        raise HTTPException(409, "запись не в очереди")
    desc = str(proposal.get("description") or "")[:24]
    return HTMLResponse(
        _oob_empty_state(request, store) + _oob_approve_all(request, store) + _oob_badge(store)
        + _oob_toast(f"Одобрено: {chosen} — {desc}"))


@router.post("/reviews/{tx_id}/skip", response_class=HTMLResponse)
async def skip_review(request: Request, tx_id: int, store: Annotated[Store, Depends(get_store)]):
    tx = store.get_transaction(tx_id)
    if not tx:
        raise HTTPException(404, "не найдено")
    if not store.skip_review(tx_id):
        raise HTTPException(409, "запись не в очереди")
    desc = str(tx.get("description") or "")[:24]
    return HTMLResponse(
        _oob_empty_state(request, store) + _oob_approve_all(request, store) + _oob_badge(store)
        + _oob_toast(f"Пропущено: {desc}"))


@router.post("/reviews/approve-all", response_class=HTMLResponse)
async def approve_all(request: Request, store: Annotated[Store, Depends(get_store)]):
    n = store.approve_all_reviews()
    return HTMLResponse(_rows_html(request, store) + _oob_approve_all(request, store)
                        + _oob_badge(store) + _oob_toast(f"Одобрено записей: {n}"))


@router.patch("/transactions/{tx_id}")
def confirm(tx_id: int, body: ConfirmIn, store: Annotated[Store, Depends(get_store)]):
    taxonomy = load_taxonomy()
    if not taxonomy.is_valid(body.category):
        raise HTTPException(422, f"категория {body.category} вне таксономии")
    ok = store.update_category(tx_id, body.category, source="correction")
    store.seed_merchant_cache(tx_id)
    if not ok:
        raise HTTPException(404, "не найдено")
    return {"ok": True, "pending_count": sum(1 for _ in store.queued_for_review())}


@router.get("/transactions/{tx_id}")
def get_one(tx_id: int, store: Annotated[Store, Depends(get_store)]):
    tx = store.get_transaction(tx_id)
    if not tx:
        raise HTTPException(404, "не найдено")
    return tx


@router.post("/import")
async def do_import(request: Request, store: Annotated[Store, Depends(get_store)]):
    taxonomy = load_taxonomy()
    ct = request.headers.get("content-type", "application/json")
    if "application/json" in ct:
        body = await _json_payload(request, ImportIn)
    else:
        # framework-дефолт 1 МБ резал форму раньше наших лимитов: поднимаем до 2×лимита,
        # чтобы превышение обрабатывал наш код (понятные 413/HTMX-сообщение)
        form = await request.form(max_part_size=2 * MAX_CSV_BYTES)
        bank = form.get("bank")
        csv = form.get("csv")
        body = ImportIn(bank=str(bank) if bank is not None else "auto",
                        csv=str(csv) if csv is not None else "")
    is_hx = request.headers.get("hx-request", "").lower() == "true"
    try:
        result = import_csv(body.csv, store, bank=body.bank, taxonomy=taxonomy)
    except ImportLimitError as e:  # лимиты импорта — понятный 413; прочие ValueError остаются багами (500)
        if is_hx:
            return HTMLResponse(f'<p class="text-red-400">Ошибка импорта: {escape(str(e))}</p>')
        raise HTTPException(413, detail=str(e)) from None
    except Exception as e:
        if is_hx:
            return HTMLResponse(f'<p class="text-red-400">Ошибка импорта: {escape(str(e))}</p>')
        raise
    if is_hx:
        if result["status"] == "format_error":
            return HTMLResponse(
                f'<p class="text-red-400">Ошибка импорта: {escape(str(result["message"]))}</p>')
        if result["status"] == "empty":
            return HTMLResponse('<p class="text-red-400">Пустой файл</p>')
        return HTMLResponse(f'<p class="text-blue-400">Импортировано: {escape(summarize(result))}</p>')
    return result