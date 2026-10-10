"""Public legal pages. No login required — §5 DDG requires the Impressum to
be reachable without hurdles (no auth wall, no more than one click away)."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gcrm.api.templates import templates
from gcrm.tools.db_offers import list_offers

logger = logging.getLogger(__name__)
router = APIRouter(tags=["legal"])


@router.get("/impressum", response_class=HTMLResponse)
def impressum_page(request: Request):
    return templates.TemplateResponse("impressum.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    """Publish the controller's privacy information without requiring login.

    The products named under "Purpose" are the controller's active offers, read
    live so a new offer is covered the moment it is added. The page must stay
    reachable even when that read fails: then it names the purpose without the
    list."""
    try:
        offers = list_offers(None)
    except Exception:
        logger.exception("privacy page: offers unavailable")
        offers = []
    return templates.TemplateResponse("privacy.html", {"request": request, "offers": offers})
