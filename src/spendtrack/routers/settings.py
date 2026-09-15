from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from spendtrack import taxonomy_repo as repo
from spendtrack.config import ROOT
from spendtrack.store import Store

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "src" / "spendtrack" / "templates")


def _store() -> Store:
    return Store()


def _context() -> dict:
    data = repo.load_raw()
    store = _store()
    usage = repo.usage_counts(store)
    store.close()
    return {
        "categories": data.get("categories", []),
        "rules": data.get("rules", []),
        "usage": usage,
        "file_hash": repo.file_hash(),
    }


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return templates.TemplateResponse(request, "settings.html", _context())


def _cats_fragment(request: Request, error: str | None = None) -> HTMLResponse:
    ctx = _context()
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/settings_categories.html", ctx)


@router.post("/settings/categories", response_class=HTMLResponse)
async def add_category(request: Request):
    form = await request.form()
    try:
        repo.add_category(str(form.get("name") or ""), str(form.get("color") or ""),
                          str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _cats_fragment(request, str(e))
    return _cats_fragment(request)


@router.post("/settings/categories/color", response_class=HTMLResponse)
async def set_color(request: Request):
    form = await request.form()
    try:
        repo.set_color(str(form.get("name") or ""), str(form.get("color") or ""),
                       str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _cats_fragment(request, str(e))
    return _cats_fragment(request)


@router.post("/settings/categories/delete", response_class=HTMLResponse)
async def delete_category(request: Request):
    form = await request.form()
    store = _store()
    try:
        repo.delete_category(str(form.get("name") or ""), store,
                             str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        store.close()
        return _cats_fragment(request, str(e))
    store.close()
    return _cats_fragment(request)


@router.post("/settings/test", response_class=HTMLResponse)
async def tester(request: Request):
    form = await request.form()
    store = _store()
    result = repo.test_description(str(form.get("description") or ""), store)
    store.close()
    return templates.TemplateResponse(request, "partials/tester_result.html", {"result": result})
