"""Customer Help Centre and admin content editor for the server-rendered UI."""
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.templates import templates
from gcrm.i18n import DEFAULT_LANGUAGE
from gcrm.tools.db_help import (
    complete_help_tour,
    has_completed_help_tour,
    list_help_for_editor,
    list_published_help,
    record_help_feedback,
    save_help_article,
)

router = APIRouter(prefix="/help", tags=["help"])
_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
_CATEGORIES = {"getting-started", "research", "outreach", "contacts", "capture", "inbox", "account", "general"}


def _language(request: Request) -> str:
    return request.session.get("ui_language", DEFAULT_LANGUAGE)


def _workspace_id(request: Request) -> int | None:
    return request.session.get("workspace_id")


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def help_centre(request: Request, q: str = ""):
    response = templates.TemplateResponse("help.html", {
        "request": request,
        "articles": list_published_help(_workspace_id(request), _language(request), "web", q),
        "query": q,
        "tour_complete": has_completed_help_tour(request.session.get("user_id")),
        "start_tour": request.query_params.get("tour") == "1",
    })
    # Published guidance must update immediately after an admin saves it.
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post("/feedback", dependencies=[Depends(require_login)])
def submit_feedback(
    request: Request,
    article_id: int = Form(...),
    helpful: str = Form(...),
    comment: str = Form(""),
):
    record_help_feedback(_workspace_id(request), article_id, request.session.get("user_id"), helpful == "yes", comment)
    return RedirectResponse("/help/", status_code=303)


@router.post("/tour/complete", dependencies=[Depends(require_login)])
def finish_tour(request: Request):
    user_id = request.session.get("user_id")
    if user_id is not None:
        complete_help_tour(user_id)
    return RedirectResponse("/help/", status_code=303)


@router.get("/manage", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def manage_help(request: Request):
    return templates.TemplateResponse("help_manage.html", {
        "request": request,
        "articles": list_help_for_editor(_workspace_id(request)),
        "error": request.session.pop("help_editor_error", ""),
    })


@router.post("/manage", dependencies=[Depends(require_admin)])
def save_article(
    request: Request,
    slug: str = Form(...),
    category: str = Form("general"),
    status: str = Form("draft"),
    surface_web: str | None = Form(None),
    surface_mobile: str | None = Form(None),
    title_en: str = Form(""), title_de: str = Form(""),
    summary_en: str = Form(""), summary_de: str = Form(""),
    body_en: str = Form(""), body_de: str = Form(""),
):
    clean_slug = slug.strip().lower()
    surfaces = [surface for surface, selected in (("web", surface_web), ("mobile", surface_mobile)) if selected]
    if not _SLUG_PATTERN.fullmatch(clean_slug) or category not in _CATEGORIES or status not in {"draft", "published"} or not surfaces:
        request.session["help_editor_error"] = "Use a unique lowercase slug, a valid category, and at least one surface."
        return RedirectResponse("/help/manage", status_code=303)
    if not title_en.strip() or not title_de.strip() or not body_en.strip() or not body_de.strip():
        request.session["help_editor_error"] = "English and German titles and bodies are required before saving."
        return RedirectResponse("/help/manage", status_code=303)
    save_help_article(_workspace_id(request), {
        "slug": clean_slug, "category": category, "surfaces": surfaces, "status": status,
        "title_en": title_en.strip(), "title_de": title_de.strip(),
        "summary_en": summary_en.strip(), "summary_de": summary_de.strip(),
        "body_en": body_en.strip(), "body_de": body_de.strip(),
    })
    return RedirectResponse("/help/manage", status_code=303)
