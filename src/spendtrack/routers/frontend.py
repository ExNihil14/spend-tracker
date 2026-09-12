from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from spendtrack.config import ROOT
from spendtrack.reports import categories_with_totals, report_month
from spendtrack.store import Store, fmt_amount
from spendtrack.taxonomy import load_taxonomy

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "src" / "spendtrack" / "templates")


def _store() -> Store:
    return Store()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, month: str | None = None, month_delta: int = 0):
    store = _store()
    taxonomy = load_taxonomy()
    current = _resolve_month(store, month, month_delta)
    transactions = store.list_transactions(month=current)
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