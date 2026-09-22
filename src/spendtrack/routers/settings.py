from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from spendtrack import taxonomy_repo as repo
from spendtrack.colors import badge_text_color
from spendtrack.config import PKG_DIR
from spendtrack.deps import get_store
from spendtrack.reports import BUDGET_EXCLUDED
from spendtrack.store import Store, fmt_amount

router = APIRouter()
templates = Jinja2Templates(directory=PKG_DIR / "templates")
templates.env.globals.update(badge_text=badge_text_color)


def _context(store: Store) -> dict:
    data = repo.load_raw()
    usage = repo.usage_counts(store)
    pending = store.pending_count()
    budgets = store.budget_map()
    analysis = repo.analyze_rules(data)
    return {
        "categories": data.get("categories", []),
        "rules": data.get("rules", []),
        "rules_view": analysis,
        "pending": [None] * pending,
        "usage": usage,
        "budgets": budgets,
        "budget_categories": [c for c in data.get("categories", [])
                              if c["name"] not in BUDGET_EXCLUDED],
        "fmt": fmt_amount,
        "file_hash": repo.file_hash(),
        "dead_count": sum(1 for a in analysis if a["dead"]),
        "duplicate_count": sum(1 for a in analysis if a["duplicate_of"] is not None),
    }


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request, store: Annotated[Store, Depends(get_store)]):
    return templates.TemplateResponse(request, "settings.html", _context(store))


def _cats_fragment(request: Request, store: Store, error: str | None = None) -> HTMLResponse:
    ctx = _context(store)
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/settings_categories.html", ctx)


@router.post("/settings/categories", response_class=HTMLResponse)
async def add_category(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.add_category(str(form.get("name") or ""), str(form.get("color") or ""),
                          str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _cats_fragment(request, store, str(e))
    return _cats_fragment(request, store)


@router.post("/settings/categories/color", response_class=HTMLResponse)
async def set_color(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.set_color(str(form.get("name") or ""), str(form.get("color") or ""),
                       str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _cats_fragment(request, store, str(e))
    return _cats_fragment(request, store)


@router.post("/settings/categories/delete", response_class=HTMLResponse)
async def delete_category(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.delete_category(str(form.get("name") or ""), store,
                             str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _cats_fragment(request, store, str(e))
    return _cats_fragment(request, store)


@router.post("/settings/categories/rename/preview", response_class=HTMLResponse)
async def rename_preview(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        preview = repo.rename_preview(str(form.get("name") or ""),
                                      str(form.get("new_name") or ""), store,
                                      str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return templates.TemplateResponse(request, "partials/rename_confirm.html",
                                          {"preview": None, "error": str(e)})
    return templates.TemplateResponse(request, "partials/rename_confirm.html",
                                      {"preview": preview, "error": None})


@router.post("/settings/categories/rename", response_class=HTMLResponse)
async def rename_category(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.rename_category(str(form.get("name") or ""), str(form.get("new_name") or ""),
                             store, str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _cats_fragment(request, store, str(e))
    return _cats_fragment(request, store)


def _budgets_fragment(request: Request, store: Store, error: str | None = None) -> HTMLResponse:
    ctx = _context(store)
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/settings_budgets.html", ctx)


@router.post("/settings/budgets", response_class=HTMLResponse)
async def set_budget(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.set_budget(str(form.get("category") or ""), str(form.get("amount") or ""), store)
    except repo.TaxonomyError as e:
        return _budgets_fragment(request, store, str(e))
    return _budgets_fragment(request, store)


def _rules_fragment(request: Request, store: Store, error: str | None = None) -> HTMLResponse:
    ctx = _context(store)
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/settings_rules.html", ctx)


def _parse_index(raw: object) -> int:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        raise repo.TaxonomyError("некорректный индекс правила") from None


@router.post("/settings/rules", response_class=HTMLResponse)
async def add_rule(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.add_rule(str(form.get("pattern") or ""), str(form.get("category") or ""),
                      str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _rules_fragment(request, store, str(e))
    return _rules_fragment(request, store)


@router.post("/settings/rules/delete", response_class=HTMLResponse)
async def delete_rule(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.delete_rule(_parse_index(form.get("index")), str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _rules_fragment(request, store, str(e))
    return _rules_fragment(request, store)


@router.post("/settings/rules/move", response_class=HTMLResponse)
async def move_rule(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    try:
        repo.move_rule(_parse_index(form.get("index")), str(form.get("direction") or ""),
                       str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _rules_fragment(request, store, str(e))
    return _rules_fragment(request, store)


@router.post("/settings/rules/preview", response_class=HTMLResponse)
async def preview_rule(request: Request):
    form = await request.form()
    pattern = str(form.get("pattern") or "")
    if len(pattern.strip()) < 2:  # не шумим ошибкой, пока пользователь печатает первый символ
        return templates.TemplateResponse(request, "partials/rule_preview.html",
                                          {"preview": None, "error": None})
    try:
        result = repo.preview_rule(pattern, str(form.get("category") or ""))
    except repo.TaxonomyError as e:
        return templates.TemplateResponse(request, "partials/rule_preview.html",
                                          {"error": str(e), "preview": None})
    return templates.TemplateResponse(request, "partials/rule_preview.html",
                                      {"preview": result, "error": None})


@router.post("/settings/test", response_class=HTMLResponse)
async def tester(request: Request, store: Annotated[Store, Depends(get_store)]):
    form = await request.form()
    result = repo.test_description(str(form.get("description") or ""), store)
    return templates.TemplateResponse(request, "partials/tester_result.html", {"result": result})
