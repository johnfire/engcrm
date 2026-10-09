"""Manual business entry on the website, sharing mobile validation."""
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_admin
from gcrm.api.routers.api_record_edit import (
    TEXT_LIMITS,
    OrganizationFields,
    save_manual_organization,
)
from gcrm.api.templates import templates
from gcrm.audit_context import audit_scope
from gcrm.i18n import translate
from gcrm.organization_state import DEFAULT_STAGE, PIPELINE_STAGES
from gcrm.sources import MANUAL_WEB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/organizations", dependencies=[Depends(require_admin)])

FIELD_LABELS = {
    "name": "common.name", "type": "common.type", "city": "common.city", "country": "common.country",
    "website": "common.website", "email": "common.email", "phone": "common.phone",
    "decision_maker": "organizationBrief.decisionMaker",
    "preferred_contact_method": "organizationDetail.preferredContact", "notes": "common.notes",
}


def render_business_form(request: Request, values: dict, error=None, status_code=200):
    existing_id = error.get("existing_id") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    return templates.TemplateResponse("organization_new.html", {
        "request": request, "values": values, "error": message, "existing_id": existing_id,
        "labels": FIELD_LABELS, "limits": TEXT_LIMITS, "stages": PIPELINE_STAGES,
    }, status_code=status_code)


@router.get("/new", response_class=HTMLResponse)
def new_business(request: Request):
    return render_business_form(request, {"country": "DE", "pipeline_stage": DEFAULT_STAGE})


@router.post("/new", response_class=HTMLResponse)
def create_business(request: Request, body: OrganizationFields = Form(...)):
    values = body.model_dump()
    actor = request.session.get("email") or "shared-admin"
    try:
        with audit_scope(actor, "user", request.state.correlation_id):
            created = save_manual_organization(body, MANUAL_WEB)
    except HTTPException as failure:
        return render_business_form(request, values, failure.detail, failure.status_code)
    except Exception:
        logger.exception("manual business creation failed")
        message = translate("businessForm.failed", request.session.get("ui_language", "en"))
        return render_business_form(request, values, message, 503)
    return RedirectResponse(f"/organizations/{created['id']}", status_code=303)
