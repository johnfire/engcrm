"""Review and correct an actual contact day on mobile and the website."""
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from gcrm.api.auth import require_admin
from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.api.templates import templates
from gcrm.audit_context import audit_scope
from gcrm.i18n import translate
from gcrm.tools.db_contact_dates import get_contact_date, parse_contact_day, set_contact_date

logger = logging.getLogger(__name__)
router = APIRouter(tags=["contact-dates"])


class ContactDateBody(BaseModel):
    contact_date: str
    interaction_id: int | None = Field(None, gt=0)
    previous_date: str | None = None


def save_contact_day(kind: str, contact_id: int, body: ContactDateBody, workspace_id: int | None) -> dict:
    selected = parse_contact_day(body.contact_date)
    return set_contact_date(kind, contact_id, selected, body.interaction_id, body.previous_date, workspace_id)


@router.get("/api/contact-feed/{kind}/{contact_id}/date", dependencies=[Depends(require_jwt_admin)])
def mobile_contact_day(kind: str, contact_id: int, payload: dict = Depends(require_jwt_payload)):
    _, workspace_id = _personal_identity(payload)
    return get_contact_date(kind, contact_id, workspace_id)


@router.patch("/api/contact-feed/{kind}/{contact_id}/date", dependencies=[Depends(require_jwt_admin)])
def mobile_save_contact_day(request: Request, kind: str, contact_id: int, body: ContactDateBody,
                            payload: dict = Depends(require_jwt_payload)):
    _, workspace_id = _personal_identity(payload)
    actor = f"user:{payload['uid']}" if payload.get("uid") is not None else "shared-admin"
    with audit_scope(actor, "user", request.state.correlation_id):
        return save_contact_day(kind, contact_id, body, workspace_id)


def render_contact_day(request: Request, record: dict, selected: str | None, error=None, status_code=200):
    return templates.TemplateResponse("contact_date.html", {
        "request": request, "contact": record, "selected": selected or "", "error": error,
    }, status_code=status_code)


@router.get("/contact-feed/{kind}/{contact_id}/date", dependencies=[Depends(require_admin)])
def web_contact_day(request: Request, kind: str, contact_id: int):
    record = get_contact_date(kind, contact_id, request.session.get("workspace_id"))
    return render_contact_day(request, record, record["contact_date"])


@router.post("/contact-feed/{kind}/{contact_id}/date", dependencies=[Depends(require_admin)])
def web_save_contact_day(request: Request, kind: str, contact_id: int, body: ContactDateBody = Form(...)):
    workspace_id = request.session.get("workspace_id")
    record = get_contact_date(kind, contact_id, workspace_id)
    reviewed = {**record, "interaction_id": body.interaction_id, "contact_date": body.previous_date}
    try:
        with audit_scope(request.session.get("email") or "shared-admin", "user", request.state.correlation_id):
            save_contact_day(kind, contact_id, body, workspace_id)
    except HTTPException as failure:
        return render_contact_day(request, reviewed, body.contact_date, failure.detail, failure.status_code)
    except Exception:
        logger.exception("contact date correction failed")
        message = translate("contactDate.failed", request.session.get("ui_language", "en"))
        return render_contact_day(request, reviewed, body.contact_date, message, 503)
    return RedirectResponse("/contact-feed/", status_code=303)
