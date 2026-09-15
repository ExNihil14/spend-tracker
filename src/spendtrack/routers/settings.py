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
    analysis = repo.analyze_rules(data)
    return {
        "categories": data.get("categories", []),
        "rules": data.get("rules", []),
        "rules_view": analysis,
        "usage": usage,
        "file_hash": repo.file_hash(),
        "dead_count": sum(1 for a in analysis if a["dead"]),
        "duplicate_count": sum(1 for a in analysis if a["duplicate_of"] is not None),
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


@router.post("/settings/categories/rename/preview", response_class=HTMLResponse)
async def rename_preview(request: Request):
    form = await request.form()
    store = _store()
    try:
        preview = repo.rename_preview(str(form.get("name") or ""),
                                      str(form.get("new_name") or ""), store,
                                      str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        store.close()
        return templates.TemplateResponse(request, "partials/rename_confirm.html",
                                          {"preview": None, "error": str(e)})
    store.close()
    return templates.TemplateResponse(request, "partials/rename_confirm.html",
                                      {"preview": preview, "error": None})


@router.post("/settings/categories/rename", response_class=HTMLResponse)
async def rename_category(request: Request):
    form = await request.form()
    store = _store()
    try:
        repo.rename_category(str(form.get("name") or ""), str(form.get("new_name") or ""),
                             store, str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        store.close()
        return _cats_fragment(request, str(e))
    store.close()
    return _cats_fragment(request)


def _rules_fragment(request: Request, error: str | None = None) -> HTMLResponse:
    ctx = _context()
    ctx["error"] = error
    return templates.TemplateResponse(request, "partials/settings_rules.html", ctx)


def _parse_index(raw: object) -> int:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        raise repo.TaxonomyError("некорректный индекс правила") from None


@router.post("/settings/rules", response_class=HTMLResponse)
async def add_rule(request: Request):
    form = await request.form()
    try:
        repo.add_rule(str(form.get("pattern") or ""), str(form.get("category") or ""),
                      str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _rules_fragment(request, str(e))
    return _rules_fragment(request)


@router.post("/settings/rules/delete", response_class=HTMLResponse)
async def delete_rule(request: Request):
    form = await request.form()
    try:
        repo.delete_rule(_parse_index(form.get("index")), str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _rules_fragment(request, str(e))
    return _rules_fragment(request)


@router.post("/settings/rules/move", response_class=HTMLResponse)
async def move_rule(request: Request):
    form = await request.form()
    try:
        repo.move_rule(_parse_index(form.get("index")), str(form.get("direction") or ""),
                       str(form.get("file_hash") or ""))
    except repo.TaxonomyError as e:
        return _rules_fragment(request, str(e))
    return _rules_fragment(request)


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
async def tester(request: Request):
    form = await request.form()
    store = _store()
    result = repo.test_description(str(form.get("description") or ""), store)
    store.close()
    return templates.TemplateResponse(request, "partials/tester_result.html", {"result": result})
