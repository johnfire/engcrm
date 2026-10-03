"""Mobile JSON API for people — the individuals on scanned cards, each linked to
their company contact. People are created via the card-confirm flow; apart from
that the phone can change a person's stage and delete them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_admin
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db import get_people, get_person
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_people import update_person
from gcrm.tools.privacy_retention import erase_person

router = APIRouter(prefix="/api/people", tags=["mobile-people"])


@router.get("")
def list_people(
    search: str = "",
    sort: str = "created_at",
    dir: str = "desc",
    _role: str = Depends(require_jwt),
) -> list[dict]:
    return get_people(search, sort, dir)


@router.get("/{person_id}")
def person_detail(person_id: int, _role: str = Depends(require_jwt)) -> dict:
    person = get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


class StageBody(BaseModel):
    stage: str | None = None  # null clears the stage


@router.patch("/{person_id}/stage")
def set_person_stage(
    person_id: int, body: StageBody, _role: str = Depends(require_jwt_admin)
) -> dict:
    """Set (or clear) the stage tag on a person. Admin only. An unknown stage is
    refused, not replaced."""
    if body.stage is not None and body.stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    try:
        updated = update_person(person_id, {"pipeline_stage": body.stage or ""})
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    if not updated:
        raise HTTPException(status_code=404, detail="Person not found")
    log_audit(None, None, "person.stage_changed", f"person:{person_id}", body.stage or "cleared")
    return {"pipeline_stage": body.stage}


@router.delete("/{person_id}")
def delete_person(person_id: int, _role: str = Depends(require_jwt_admin)) -> dict:
    """Permanently delete one person (admin only, no undo)."""
    if not erase_person(person_id):
        raise HTTPException(status_code=404, detail="Person not found")
    return {"deleted": True}
