from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from spendtrack.config import ROOT
from spendtrack.reports import categories_with_totals, report_daily, report_month
from spendtrack.store import Store, fmt_amount
from spendtrack.taxonomy import load_taxonomy

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "src" / "spendtrack" / "templates")


def _store() -> Store:
    return Store()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, month: str | None = None, month_delta: int = 0,
          category: str | None = None, q: str | None = None):
    store = _store()
    taxonomy = load_taxonomy()
    current = _resolve_month(store, month, month_delta)
    transactions = store.list_transactions(month=current, category=category or None, search=q or None)
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
            "cat_colors": cats,
            "all_categories": [c.name for c in taxonomy.categories],
            "category": category or "",
            "q": q or "",
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
    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "report": report,
            "daily": daily,
            "current": current,
            "fmt": fmt_amount,
            "cat_colors": cats,
            "categories_json": [dict(c) for c in report["categories"]],
            "daily_json": daily,
            "colors_json": colors,
        },
    )


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