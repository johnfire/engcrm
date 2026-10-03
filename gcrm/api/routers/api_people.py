"""Mobile JSON API for people — the individuals on scanned cards, each linked to
their company contact. People arrive through the card-confirm flow or are added by
hand here; the phone can also edit them, change their stage, and delete them."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_admin, require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.api.routers.api_record_edit import clean_fields
from gcrm.db.connection import db
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db import get_people, get_person
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_people import find_existing_person, save_person, update_person
from gcrm.tools.privacy_retention import erase_person

router = APIRouter(prefix="/api/people", tags=["mobile-people"])


PAGE_SIZE = 50


@router.get("")
def list_people(
    search: str = "",
    sort: str = "created_at",
    dir: str = "desc",
    stage: str = "",
    linkedin: str = "",
    page: int | None = Query(default=None, ge=1),
    _role: str = Depends(require_jwt),
) -> list[dict]:
    """People, newest first by default. `stage` is a pipeline stage or "none" (no
    stage set); `linkedin` is "1" (LinkedIn connections) or "unlinked" (connections
    not yet tied to an organization). Without `page` the whole list comes back, as
    older app builds expect; with it, one page of PAGE_SIZE."""
    if stage and stage != "none" and stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    if linkedin not in ("", "1", "unlinked"):
        raise HTTPException(status_code=400, detail="Unknown linkedin filter")
    paging = {} if page is None else {"limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE}
    return get_people(search, sort, dir, linkedin=linkedin, stage=stage, **paging)


# column -> maximum length. people.name and people.email are VARCHAR(200); the rest
# are TEXT and capped here only so a runaway paste cannot fill the table.
PERSON_LIMITS = {
    "name": 200, "title": 200, "email": 200, "phone": 60, "website": 300,
    "city": 100, "country": 2, "relationship": 100, "met_at": 200,
    "notes": 20000, "linkedin_url": 300,
}


class PersonFields(BaseModel):
    """Every field optional: create needs `name`, edit sends what changed."""
    name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    city: str | None = None
    country: str | None = None
    relationship: str | None = None
    met_at: str | None = None
    notes: str | None = None
    linkedin_url: str | None = None
    # create only: the organization this person works at
    contact_id: int | None = None


def _organization_exists(contact_id: int, workspace_id: int | None) -> bool:
    scope = "AND workspace_id = %s" if workspace_id is not None else ""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT 1 FROM contacts WHERE id = %s AND deleted_at IS NULL {scope}",
            [contact_id] + ([workspace_id] if workspace_id is not None else []),
        )
        return cur.fetchone() is not None


@router.post("")
def create_person(
    body: PersonFields,
    _role: str = Depends(require_jwt_admin),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    """Add a person by hand, optionally at an organization. A person who already
    exists (same email, or same name at the same organization) is reported with a
    409 and their id — the typed details are not merged into them or dropped
    silently."""
    fields = clean_fields(body, PERSON_LIMITS, require_name=True)
    if fields.get("linkedin_url"):
        # Validate before saving: save_person does not take a linkedin_url.
        from gcrm.linkedin import normalize_linkedin_url
        if normalize_linkedin_url(fields["linkedin_url"]) is None:
            raise HTTPException(status_code=400, detail="LinkedIn URL must be a linkedin.com link")
    if body.contact_id is not None:
        _, workspace_id = _personal_identity(payload)
        if not _organization_exists(body.contact_id, workspace_id):
            raise HTTPException(status_code=404, detail="Organization not found")
    with db() as conn:
        existing_id = find_existing_person(
            conn.cursor(), fields["name"], fields.get("email") or "", body.contact_id
        )
    if existing_id:
        raise HTTPException(status_code=409, detail={
            "message": "This person already exists", "existing_id": existing_id,
        })
    person_id = save_person(
        fields["name"],
        title=fields.get("title") or "", email=fields.get("email") or "",
        phone=fields.get("phone") or "", website=fields.get("website") or "",
        city=fields.get("city") or "", country=fields.get("country") or "DE",
        relationship=fields.get("relationship") or "", notes=fields.get("notes") or "",
        met_at=fields.get("met_at") or "", contact_id=body.contact_id, source="manual",
    )
    if fields.get("linkedin_url"):
        update_person(person_id, {"linkedin_url": fields["linkedin_url"]})
    log_audit(None, None, "person.created", f"person:{person_id}", "created")
    return {"id": person_id}


@router.patch("/{person_id}")
def edit_person(
    person_id: int, body: PersonFields, _role: str = Depends(require_jwt_admin)
) -> dict:
    """Change the fields sent; leave every other field alone."""
    fields = clean_fields(body, PERSON_LIMITS, require_name=False)
    if body.contact_id is not None:
        raise HTTPException(status_code=400, detail="The organization is not changed here")
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to change")
    try:
        updated = update_person(person_id, {k: v or "" for k, v in fields.items()})
    except ValueError:
        raise HTTPException(status_code=400, detail="LinkedIn URL must be a linkedin.com link")
    if not updated:
        raise HTTPException(status_code=404, detail="Person not found")
    log_audit(None, None, "person.edited", f"person:{person_id}", ",".join(sorted(fields)))
    return {"id": person_id, "changed": sorted(fields)}


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
