from __future__ import annotations

import logging
from datetime import date
from decimal import InvalidOperation
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from spendtrack import errors
from spendtrack.assets import static_url
from spendtrack.cat_icons import cat_icon
from spendtrack.categorize import categorize_transaction
from spendtrack.colors import badge_text_color
from spendtrack.config import PKG_DIR
from spendtrack.csv_import import (
    MAX_AMOUNT_KOPECKS,
    MAX_CSV_BYTES,
    ImportLimitError,
    import_csv,
    summarize,
)
from spendtrack.deps import get_store
from spendtrack.goals import goals_snapshot
from spendtrack.reports import budgets_progress
from spendtrack.store import (
    Store,
    conf_level,
    currency_symbol,
    fmt_amount,
    fmt_date,
    fmt_money,
    fmt_month,
    normalize_currency,
    parse_amount,
    valid_month,
)
from spendtrack.taxonomy import load_taxonomy
from spendtrack.ui import oob_toast

router = APIRouter()
templates = Jinja2Templates(directory=PKG_DIR / "templates")
templates.env.globals.update(
    fmt_money=fmt_money, fmt_month=fmt_month, fmt_date=fmt_date, conf_level=conf_level,
    badge_text=badge_text_color, static=static_url, cat_icon=cat_icon,
    currency_symbol=currency_symbol,
)


class TxIn(BaseModel):
    date: str
    description: str = Field(max_length=512)  # F8: без лимита мусор любого размера едет в БД и отчёты
    amount: str = Field(max_length=64)
    account: str | None = Field(default=None, max_length=128)
    currency: str | None = None

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        try:
            # F1: date.fromisoformat (3.11+) принимает и «20260912»/«2026-W37-6» — нормализуем к
            # YYYY-MM-DD, иначе запись молча выпадает из месячных срезов и бюджетов.
            return date.fromisoformat(v).isoformat()
        except ValueError as e:
            raise ValueError("дата — в формате ГГГГ-ММ-ДД") from e

    @field_validator("amount")
    @classmethod
    def _valid_amount(cls, v: str) -> str:
        try:
            kopecks = parse_amount(v)  # аудит 24.09: «abc» давало 500 вместо 422
        except (InvalidOperation, ValueError, OverflowError) as e:
            raise ValueError(errors.text("amount_unrecognized")) from e
        # Dash 4.8: тот же санитарный лимит, что у CSV-импорта (MAX_AMOUNT_KOPECKS) —
        # один вход не должен принимать то, что другой молча отбрасывает; int64-безопасность сохраняется.
        if not -MAX_AMOUNT_KOPECKS <= kopecks <= MAX_AMOUNT_KOPECKS:
            raise ValueError(
                f"сумма сверх лимита на операцию (до {fmt_money(MAX_AMOUNT_KOPECKS, signed=False)})")
        return v

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None  # пусто → базовая валюта настроек (резолвится в Store)
        code = normalize_currency(value)
        if code is None:
            raise ValueError("Неизвестная валюта (ожидается код ISO 4217, например RUB/USD/EUR)")
        return code


class ConfirmIn(BaseModel):
    category: str


class GoalIn(BaseModel):
    """JSON-создание цели (CLI/тесты); htmx-форма идёт мимо модели — из form-data."""

    title: str = Field(max_length=120)
    target: str = Field(max_length=64)  # строка как у TxIn.amount: парсим в копейки
    currency: str | None = None
    due_month: str | None = None

    @field_validator("target")
    @classmethod
    def _valid_target(cls, v: str) -> str:
        try:
            kopecks = parse_amount(v)
        except (InvalidOperation, ValueError, OverflowError) as e:
            raise ValueError(errors.text("goal_amount_unrecognized")) from e
        if not 0 < kopecks <= MAX_AMOUNT_KOPECKS:
            raise ValueError(f"сумма цели — больше нуля и до {fmt_money(MAX_AMOUNT_KOPECKS, signed=False)}")
        return v

    @field_validator("currency")
    @classmethod
    def _valid_goal_currency(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None  # пусто → базовая валюта настроек (резолвится в Store)
        code = normalize_currency(value)
        if code is None:
            raise ValueError("Неизвестная валюта (ожидается код ISO 4217, например RUB/BYN)")
        return code


class ImportIn(BaseModel):
    bank: str = "auto"
    csv: str


def _validation_422(exc: ValidationError) -> HTTPException:
    """422 с безопасными ctx (объект исключения кастомного валидатора не сериализуется → 500).

    Эхо `input` обрезается: иначе поле на мегабайты целиком уезжает в ответ (ревью web_api).
    """
    errors = []
    for err in exc.errors():
        if isinstance(err.get("ctx"), dict):
            err = {**err, "ctx": {k: str(v) for k, v in err["ctx"].items()}}
        if "input" in err:
            err["input"] = str(err["input"])[:200]
        errors.append(err)
    return HTTPException(422, detail=errors)


# Dash 4.8 (тикет 03.10): тело /api/transactions ограничено ДО чтения JSON — поля ≤512 символов,
# гигабайты в память ради последующего 422 не читаем.
MAX_JSON_BYTES = 64 * 1024


async def _json_payload[T: BaseModel](request: Request, model: type[T]) -> T:
    """Разбор JSON-тела: битая кодировка/не-объект → 400, неверные поля → 422 (а не 500)."""
    try:
        data = await request.json()
    except ValueError as e:  # JSONDecodeError/UnicodeDecodeError — тело не UTF-8/не JSON
        raise HTTPException(400, detail="Тело запроса — некорректный JSON (ожидается UTF-8)") from e
    if not isinstance(data, dict):  # F2: `"x"`/`[]`/`null`/`5` → TypeError у model(**data) — 500 без гейта
        raise HTTPException(400, detail="Тело запроса — JSON-объект {…}")
    try:
        return model(**data)
    except ValidationError as e:
        raise _validation_422(e) from e


@router.post("/transactions")
async def create(request: Request, store: Annotated[Store, Depends(get_store)]):
    taxonomy = load_taxonomy()
    ct = request.headers.get("content-type", "application/json")
    if "application/json" in ct:
        try:
            clen = int(request.headers.get("content-length") or 0)
        except ValueError:
            clen = 0
        if clen > MAX_JSON_BYTES:  # Dash 4.8: лимит до парсинга (413 вместо чтения в память)
            raise HTTPException(413, detail=f"тело превышает {MAX_JSON_BYTES // 1024} КБ")
        tx = await _json_payload(request, TxIn)
    else:
        form = await request.form()
        payload = {k: str(v) for k, v in
                   ((k, form.get(k)) for k in ("date", "description", "amount", "account", "currency"))
                   if v not in (None, "")}  # F6: пустое поле формы ≠ «не передано»
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
        desc = escape(tx.description)  # аудит 24.09: описание — пользовательский ввод, экранируем
        label = escape(category["category"])
        if category["source"] == "llm_pending_review":
            msg = (f"Добавлено: {desc} → <b>{label}</b> "
                   f"(conf {category['confidence']:.2f}), ждёт подтверждения.")
        else:
            msg = f"Добавлено: {desc} → <b>{label}</b>"
        return HTMLResponse(f'<p class="text-accent">{msg}</p>' + _oob_badge(store))
    return {"id": tx_id, **category}


@router.get("/budgets")
def budgets(store: Annotated[Store, Depends(get_store)], month: str | None = None):
    """Прогресс по бюджетам за месяц (по умолчанию — месяц последней транзакции)."""
    taxonomy = load_taxonomy()
    if month and not valid_month(month):
        raise HTTPException(422, "month — формат YYYY-MM")  # аудит 24.09: мусор → 422, не 500
    if not month:
        row = store.conn.execute("SELECT MAX(date) m FROM transactions").fetchone()
        month = (row["m"] or date.today().isoformat())[:7]  # noqa: DTZ011 — календарная ЛОКАЛЬНАЯ дата намеренно (UTC тут был багом, ревью web_api)
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
    return HTMLResponse(_oob_badge(store))  # разметка бейджа — в одном месте (без дрейфа классов/id)


def _oob_badge(store: Store) -> str:
    n = store.pending_count()
    return (
        '<span id="pending-count" hx-swap-oob="true"'
        ' class="chip-pop ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-warn-soft text-warn">'
        f"{n}</span>"
    )


def _rows_html(request: Request, store: Store) -> str:
    """Единый рендер фрагмента очереди (страница и htmx-ответы совпадают)."""
    taxonomy = load_taxonomy()
    return templates.TemplateResponse(
        request, "partials/review_rows.html",
        {"pending": store.queued_for_review(), "fmt": fmt_amount,
         "catname": taxonomy.display,
         "all_categories": [c.name for c in taxonomy.categories]},
    ).body.decode()


def _oob_approve_all(request: Request, store: Store) -> str:
    """OOB: кнопка «Одобрить все ≥ порога» живёт/исчезает вместе с очередью."""
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
        + oob_toast(f"Одобрено: {chosen} — {desc}"))


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
        + oob_toast(f"Пропущено: {desc}"))


@router.post("/reviews/approve-all", response_class=HTMLResponse)
async def approve_all(request: Request, store: Annotated[Store, Depends(get_store)]):
    """Пакетное одобрение; `min_confidence` (0..1) — только записи не ниже порога (дизайн-ревью M-4)."""
    form = await request.form()
    try:
        min_conf = float(str(form.get("min_confidence") or 0))
    except ValueError:
        raise HTTPException(422, "min_confidence — число от 0 до 1") from None
    if not 0 <= min_conf <= 1:
        raise HTTPException(422, "min_confidence — число от 0 до 1")
    known = {c.name for c in load_taxonomy().categories}
    n = store.approve_all_reviews(min_confidence=min_conf, known=known)
    suffix = f" (уверенность ≥ {round(min_conf * 100)}%)" if min_conf > 0 else ""
    return HTMLResponse(_rows_html(request, store) + _oob_approve_all(request, store)
                        + _oob_badge(store) + oob_toast(f"Одобрено записей: {n}{suffix}"))


@router.patch("/transactions/{tx_id}")
def confirm(tx_id: int, body: ConfirmIn, store: Annotated[Store, Depends(get_store)]):
    taxonomy = load_taxonomy()
    if not taxonomy.is_valid(body.category):
        raise HTTPException(422, f"категория {body.category} вне таксономии")
    # F4: коррекция снимает запись с очереди (approve_review — no-op вне очереди): иначе
    # pending-запись остаётся в очереди и следующий approve-all затрёт ручное решение LLM-догадкой.
    store.approve_review(tx_id, body.category)
    ok = store.update_category(tx_id, body.category, source="correction")
    if not ok:
        raise HTTPException(404, "не найдено")
    store.seed_merchant_cache(tx_id)  # после проверки ok: по несуществующей записи кэш не сеем
    return {"ok": True, "pending_count": store.pending_count()}


class TxOut(BaseModel):
    """Публичное представление транзакции (тикет 03.10): стабильный whitelist полей без внутрянки.

    Не отдаём: fingerprint, account_anon, export_rowid, import_batch — служебные поля
    дедупа/импорта/псевдонимизации (ADJUDICATION_WEB_API: get_one).
    """

    id: int
    date: str
    description: str
    amount_kopecks: int
    currency: str | None = None
    category: str
    category_llm: str | None = None
    category_source: str
    confidence: float
    merchant: str | None = None
    review_status: str
    created: str | None = None
    updated: str | None = None


@router.get("/transactions/{tx_id}", response_model=TxOut)
def get_one(tx_id: int, store: Annotated[Store, Depends(get_store)]):
    tx = store.get_transaction(tx_id)
    if not tx:
        raise HTTPException(404, "не найдено")
    return tx


async def _read_form_payload(request: Request) -> tuple[str, str | bytes, str]:
    """form-urlencoded | multipart (file=CSV-файл, M-6): банк+CSV. Лимит — наш, не starlette.

    Поле/часть > max_part_size: starlette конвертирует MultiPartException в СВОЙ HTTPException(400)
    (родитель fastapi.HTTPException — «except HTTPException» его не ловит, ревью web_api).
    Переводим в ImportLimitError → те же ветки 413/HX-фрагмент, что у файла выше лимита.
    Форма закрывается явно: SpooledTemporaryFile >1 МБ не должен ждать GC.
    """
    form = None
    try:
        # framework-дефолт 1 МБ резал форму раньше наших лимитов: поднимаем до 2×лимита
        form = await request.form(max_part_size=2 * MAX_CSV_BYTES)
        bank = str(form.get("bank") or "auto")
        upload = form.get("file")
        if upload is not None and getattr(upload, "filename", ""):
            return bank, await upload.read(), str(upload.filename)  # байты: utf-8-sig/cp1251-фолбэк внутри
        return bank, str(form.get("csv") or ""), "form.csv"
    except (StarletteHTTPException, MultiPartException) as e:
        mb = 2 * MAX_CSV_BYTES // (1024 * 1024)
        raise ImportLimitError(f"тело превышает лимит ({mb} МБ)") from e
    finally:
        if form is not None:
            await form.close()


def _import_limit_error(msg: str, is_hx: bool) -> HTMLResponse:
    """Лимит тела импорта: htmx — дружелюбный фрагмент, API — сырой 413 (единая точка)."""
    if is_hx:
        return HTMLResponse(f'<p class="text-danger">Ошибка импорта: {escape(msg)}</p>')
    raise HTTPException(413, detail=msg)


@router.post("/import")
async def do_import(request: Request, store: Annotated[Store, Depends(get_store)]):  # noqa: C901 — 11 (было 12); ветки формата/лимитов/HX осознанны
    """JSON | form-urlencoded | multipart — единый результат ImportOut/htmx."""
    taxonomy = load_taxonomy()
    ct = request.headers.get("content-type", "application/json")
    is_hx = request.headers.get("hx-request", "").lower() == "true"
    try:
        if "application/json" in ct:
            try:
                clen = int(request.headers.get("content-length") or 0)
            except ValueError:
                clen = 0
            if clen > 2 * MAX_CSV_BYTES:  # аудит 24.09: JSON читался целиком без лимита
                msg = f"тело превышает {2 * MAX_CSV_BYTES // (1024 * 1024)} МБ"
                return _import_limit_error(msg, is_hx)
            body = await _json_payload(request, ImportIn)
            raw: str | bytes = body.csv
            bank, filename = body.bank, "api.json"
        else:
            bank, raw, filename = await _read_form_payload(request)
        result = import_csv(raw, store, bank=bank, taxonomy=taxonomy, filename=filename)
    except ImportLimitError as e:  # лимиты импорта — понятный 413; прочие ValueError остаются багами (500)
        if is_hx:
            return HTMLResponse(f'<p class="text-danger">Ошибка импорта: {escape(str(e))}</p>')
        raise HTTPException(413, detail=str(e)) from None
    except StarletteHTTPException:
        raise  # валидационные 400/413 тела (JSON/form) — не «сбой импорта», без лога
    except Exception as e:
        # F5: без лога это глушитель — сбой превращается в зелёный 200 без следа
        logging.getLogger("spendtrack").exception("import failed: %s", filename)
        if is_hx:
            return HTMLResponse(f'<p class="text-danger" role="alert">Ошибка импорта: {escape(str(e))}</p>')
        raise
    if is_hx:
        if result["status"] == "format_error":
            return HTMLResponse(
                f'<p class="text-danger" role="alert">Ошибка импорта: {escape(str(result["message"]))}</p>')
        if result["status"] == "empty":
            return HTMLResponse('<p class="text-danger" role="alert">Пустой файл</p>')
        return HTMLResponse(f'<p class="text-info">Импортировано: {escape(summarize(result))}</p>')
    return result


# ---- цели/копилки (Ф1: страница /goals + htmx-формы; движок — Ф2) ----

def _goals_payload(request: Request, store: Store, *, error: str = "", toast: str = "") -> str:
    """Ответ мутаций целей: список + OOB-контейнер портфеля (S9) + OOB-ошибка + тост."""
    snap = goals_snapshot(store)
    parts = [templates.TemplateResponse(request, "partials/goals_list.html", snap).body.decode()]
    parts.append(templates.TemplateResponse(
        request, "partials/goals_portfolio.html", {**snap, "oob": True}).body.decode())
    parts += [_goals_error(error)]
    if toast:
        parts.append(oob_toast(toast))
    return "".join(parts)


def _goals_error(message: str) -> str:
    """OOB-ошибка в слот `#goals-error`: список целей НЕ затирается (ревью wave5, C2)."""
    text = f"Не получилось: {escape(message)}" if message else ""
    return (f'<p id="goals-error" hx-swap-oob="true" class="text-danger text-sm mb-2" '
            f'role="alert">{text}</p>')


@router.post("/goals")
async def create_goal(request: Request, store: Annotated[Store, Depends(get_store)]):
    """Создать цель: JSON → {"id": N}; htmx-форма → обновлённый список + toast."""
    ct = request.headers.get("content-type", "application/json")
    if "application/json" in ct:
        data = await _json_payload(request, GoalIn)
        try:
            gid = store.add_goal(data.title, parse_amount(data.target),
                                 currency=data.currency, due_month=data.due_month)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        return {"id": gid}
    form = await request.form()
    try:
        store.add_goal(str(form.get("title") or ""),
                       parse_amount(str(form.get("target") or "")),
                       currency=str(form.get("currency") or "") or None,
                       due_month=str(form.get("due_month") or "") or None)
    except (ValueError, InvalidOperation) as e:
        return HTMLResponse(_goals_payload(request, store, error=str(e) or "проверьте поля"))
    return HTMLResponse(_goals_payload(request, store, toast="Цель создана"))


@router.post("/goals/{goal_id}/allocate")
async def allocate_goal(request: Request, goal_id: int, store: Annotated[Store, Depends(get_store)]):
    """Взнос (>0) или изъятие (<0); дата по умолчанию — сегодня."""
    form = await request.form()
    try:
        store.add_allocation(goal_id, str(form.get("date") or "") or date.today().isoformat(),  # noqa: DTZ011 — локальная дата формы
                             parse_amount(str(form.get("amount") or "")))
    except (ValueError, InvalidOperation) as e:
        # wave5 S8: при ошибке список НЕ перерисовывается (иначе теряются черновик, дата и фокус) —
        # только OOB-ошибка; HX-Reswap: none отменяет основной свап
        return HTMLResponse(_goals_error(str(e) or "проверьте поля"),
                            headers={"HX-Reswap": "none"})
    return HTMLResponse(_goals_payload(request, store, toast="Взнос записан"))


@router.post("/goals/{goal_id}/archive")
async def archive_goal(request: Request, goal_id: int, store: Annotated[Store, Depends(get_store)]):
    if not store.archive_goal(goal_id):
        return HTMLResponse(_goals_payload(request, store, error="цель не найдена"))
    return HTMLResponse(_goals_payload(request, store, toast="Цель в архиве"))