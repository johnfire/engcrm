"""Public legal pages. No login required — §5 DDG requires the Impressum to
be reachable without hurdles (no auth wall, no more than one click away)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gcrm.api.templates import templates

router = APIRouter(tags=["legal"])


@router.get("/impressum", response_class=HTMLResponse)
def impressum_page(request: Request):
    return templates.TemplateResponse("impressum.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    """Publish the controller's privacy information without requiring login."""
    return templates.TemplateResponse("privacy.html", {"request": request})
