from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from spendtrack.config import ROOT
from spendtrack.recurring import recurring_summary
from spendtrack.reports import (
    budgets_progress,
    categories_with_totals,
    report_daily,
    report_month,
)
from spendtrack.store import Store, fmt_amount
from spendtrack.taxonomy import load_taxonomy

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "src" / "spendtrack" / "templates")

PAGE_DAYS = 31  # размер keyset-страницы списка транзакций (целыми днями)


def _store() -> Store:
    return Store()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, month: str | None = None, month_delta: int = 0,
          category: str | None = None, q: str | None = None, sort: str | None = None):
    store = _store()
    taxonomy = load_taxonomy()
    current = _resolve_month(store, month, month_delta)
    sort = sort if sort in ("recent", "amount") else "recent"
    has_more = False
    next_after: str | None = None
    if sort == "recent":
        # keyset-страница целыми днями (готовность к большим спискам; «показать ещё» — sentinel)
        transactions, next_after, has_more = store.list_transactions_days(
            month=current, category=category or None, search=q or None, days=PAGE_DAYS)
    else:
        transactions = store.list_transactions(month=current, category=category or None,
                                               search=q or None, sort=sort)
    group_days = sort == "recent"  # группировка только в хронологии (см. брейншторм 14.09)
    day_totals: dict[str, int] = {}
    if group_days:
        for t in transactions:
            day_totals[t["date"]] = day_totals.get(t["date"], 0) + t["amount_kopecks"]
    pending = store.queued_for_review()
    report = report_month(store, current)
    totals = categories_with_totals(store, current)
    cats = {c.name: c.color for c in taxonomy.categories}

    return templates.TemplateResponse(
        request, "index.html",
        {
            "transactions": transactions,
            "pending": pending,
            "report": report,
            "totals": totals,
            "current": current,
            "prev_month": _shift_month(current, -1),
            "next_month": _shift_month(current, 1),
            "cat_colors": cats,
            "all_categories": [c.name for c in taxonomy.categories],
            "category": category or "",
            "q": q or "",
            "sort": sort,
            "group_days": group_days,
            "day_totals": day_totals,
            "has_more": has_more,
            "more_url": _more_url(current, category, q, sort, next_after, PAGE_DAYS) if has_more else None,
            "fmt": fmt_amount,
        },
    )


@router.get("/approve", response_class=HTMLResponse)
def approve(request: Request):
    store = _store()
    taxonomy = load_taxonomy()
    pending = store.queued_for_review()
    cats = {c.name: c.color for c in taxonomy.categories}
    return templates.TemplateResponse(
        request, "approve.html",
        {"pending": pending, "cat_colors": cats, "fmt": fmt_amount,
         "all_categories": [c.name for c in taxonomy.categories]},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, month: str | None = None, month_delta: int = 0):
    store = _store()
    taxonomy = load_taxonomy()
    current = _resolve_month(store, month, month_delta)
    report = report_month(store, current)
    daily = report_daily(store, current)
    cats = {c.name: c.color for c in taxonomy.categories}
    colors = [cats.get(c["category"], "#9ca3af") for c in report["categories"]]
    budgets = budgets_progress(store, current, known=set(cats))
    recurring = recurring_summary(store)
    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "report": report,
            "daily": daily,
            "budgets": budgets,
            "recurring": recurring,
            "current": current,
            "prev_month": _shift_month(current, -1),
            "next_month": _shift_month(current, 1),
            "pending": store.queued_for_review(),
            "fmt": fmt_amount,
            "cat_colors": cats,
            "categories_json": [dict(c) for c in report["categories"]],
            "daily_json": daily,
            "colors_json": colors,
        },
    )


def _more_url(month: str | None, category: str | None, q: str | None,
              sort: str, after: str | None, days: int) -> str:
    params: dict[str, str] = {"sort": sort, "days": str(days)}
    if month:
        params["month"] = month
    if category:
        params["category"] = category
    if q:
        params["q"] = q
    if after:
        params["after"] = after
    return "/transactions/more?" + urlencode(params)


@router.get("/transactions/more", response_class=HTMLResponse)
def more_rows(request: Request, month: str | None = None, category: str | None = None,
              q: str | None = None, sort: str = "recent", after: str | None = None,
              days: int = PAGE_DAYS):
    """Keyset-догрузка целыми днями (htmx sentinel): rows + итоги + следующий sentinel."""
    days = max(1, min(int(days), 92))
    store = _store()
    taxonomy = load_taxonomy()
    rows, next_after, has_more = store.list_transactions_days(
        month=month or None, category=category or None, search=q or None,
        days=days, after_date=after or None)
    day_totals: dict[str, int] = {}
    for t in rows:
        day_totals[t["date"]] = day_totals.get(t["date"], 0) + t["amount_kopecks"]
    cats = {c.name: c.color for c in taxonomy.categories}
    return templates.TemplateResponse(
        request, "partials/tx_rows.html",
        {"transactions": rows, "day_totals": day_totals, "group_days": True,
         "cat_colors": cats, "fmt": fmt_amount,
         "has_more": has_more,
         "more_url": _more_url(month, category, q, sort, next_after, days)},
    )


def _shift_month(month: str, delta: int) -> str:
    """YYYY-MM ± delta (абсолютные ссылки навигации, а не относительные)."""
    idx = int(month[:4]) * 12 + int(month[5:7]) - 1 + delta
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def _resolve_month(store: Store, month: str | None, delta: int) -> str:
    import datetime as dt
    if month:
        base = dt.date(int(month[:4]), int(month[5:7]), 1)
    else:
        row = store.conn.execute("SELECT MAX(date) m FROM transactions").fetchone()
        m = (row["m"] or "")[:7]
        base = dt.date.fromisoformat(m + "-01") if m else dt.datetime.now(tz=dt.UTC).date().replace(day=1)
    target = base.replace(year=base.year + ((base.month - 1 + delta) // 12),
                          month=(base.month - 1 + delta) % 12 + 1)
    return target.strftime("%Y-%m")