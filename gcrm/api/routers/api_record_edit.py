"""Mobile JSON API: create and edit organizations (contacts) by hand.

The web app has no "new organization" form, so the phone's is new; the edit rules
mirror the web edit form. Differences, all deliberate:

  * PATCH touches only the fields the phone sends. The web form posts every field,
    so a stale form can overwrite a newer value; here a field that is not sent is
    never written.
  * Limits are checked up front. The columns are VARCHAR(n) and `country` is a
    CHAR(2) with a CHECK constraint, so an over-long value would be a 500 from
    the database instead of a message the user can act on.
  * A changed city or country clears the stored coordinates (re-geocoded when
    possible). Distance-from-home sorts on them; blank is better than the old
    city's position.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_organizations import save_organization, set_suppression_flag
from gcrm.tools.search import geocode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["mobile-contacts"])

# column -> maximum length, taken from the contacts table. Anything not listed is
# not editable from the phone.
TEXT_LIMITS = {
    "name": 200, "type": 60, "city": 100, "country": 2, "website": 300, "email": 200,
    "phone": 60, "decision_maker": 200, "preferred_contact_method": 60, "notes": 20000,
}


class OrganizationFields(BaseModel):
    """Every field optional: create needs `name`, edit sends what changed."""
    name: str | None = None
    type: str | None = None
    city: str | None = None
    country: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    decision_maker: str | None = None
    preferred_contact_method: str | None = None
    notes: str | None = None
    do_not_contact: bool | None = None


def clean_fields(body: BaseModel, limits: dict[str, int], *, require_name: bool) -> dict:
    """The submitted text fields, stripped and checked. A blank value is None (the
    column is cleared); a name may never be blank. Raises HTTPException(400)."""
    cleaned: dict = {}
    for column in limits:
        if column not in body.model_fields_set:
            continue
        value = (getattr(body, column) or "").strip()
        if column == "country":
            value = value.upper()
        if len(value) > limits[column]:
            raise HTTPException(status_code=400, detail=f"{column} is too long (max {limits[column]})")
        if column == "country" and value and (len(value) != 2 or not value.isalpha()):
            raise HTTPException(status_code=400, detail="country must be a 2-letter code, e.g. DE")
        if column == "email" and value and ("@" not in value or " " in value):
            raise HTTPException(status_code=400, detail="That email address does not look right")
        cleaned[column] = value or None
    if require_name and not cleaned.get("name"):
        raise HTTPException(status_code=400, detail="Name is required")
    if "name" in cleaned and not cleaned["name"]:
        raise HTTPException(status_code=400, detail="Name is required")
    return cleaned


def _existing_organization(name: str, city: str, email: str) -> dict | None:
    """The row save_organization would have collided with: same email, else same
    name in the same city. Mirrors its two checks."""
    with db() as conn:
        cur = conn.cursor()
        if email:
            cur.execute(
                "SELECT id, name, city, deleted_at FROM contacts "
                "WHERE lower(email) = lower(%s) AND deleted_at IS NULL LIMIT 1",
                (email,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
        cur.execute(
            "SELECT id, name, city, deleted_at FROM contacts "
            "WHERE lower(name) = lower(%s) AND lower(city) = lower(%s) "
            "ORDER BY (deleted_at IS NOT NULL) LIMIT 1",
            (name, city),
        )
        row = cur.fetchone()
        return dict(row) if row else None


@router.post("")
def create_organization(
    body: OrganizationFields,
    _role: str = Depends(require_jwt_admin),
) -> dict:
    """Add an organization by hand. It enters as a candidate, like every other
    new organization. An organization that already exists (same email, or same
    name in the same city) is reported with a 409 and its id, never overwritten
    and never silently duplicated."""
    fields = clean_fields(body, TEXT_LIMITS, require_name=True)
    name = fields["name"]
    city = fields.get("city") or ""
    email = fields.get("email") or ""
    existing = _existing_organization(name, city, email)
    if existing:
        raise HTTPException(status_code=409, detail={
            "message": "This organization already exists",
            "existing_id": None if existing["deleted_at"] else existing["id"],
            "existing_name": existing["name"],
            "existing_city": existing["city"],
        })
    contact_id = save_organization(
        name, city,
        country=fields.get("country") or "DE",
        type=fields.get("type") or "",
        website=fields.get("website") or "",
        email=email,
        phone=fields.get("phone") or "",
        notes=fields.get("notes") or "",
    )
    if not contact_id:
        # save_organization refuses names on the ignored-chains list and returns 0.
        raise HTTPException(status_code=409, detail={
            "message": "This name is on the ignored-chains list, so it was not added",
            "existing_id": None,
        })
    extras = {k: fields[k] for k in ("decision_maker", "preferred_contact_method") if fields.get(k)}
    if extras:
        _write_columns(contact_id, extras, None)
    if body.do_not_contact:
        set_suppression_flag(contact_id, "do_not_contact", True)
    return {"id": contact_id}


def _write_columns(contact_id: int, columns: dict, workspace_id: int | None) -> bool:
    """UPDATE the given columns. The names come from TEXT_LIMITS / constants in
    this module, never from the request, so the f-string is safe."""
    assignments = ", ".join(f"{column} = %s" for column in columns)
    scope = " AND workspace_id = %s" if workspace_id is not None else ""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {assignments}, updated_at = NOW() "
            f"WHERE id = %s AND deleted_at IS NULL{scope}",
            list(columns.values()) + [contact_id] + ([workspace_id] if workspace_id is not None else []),
        )
        return cur.rowcount > 0


@router.patch("/{contact_id}")
def edit_organization(
    contact_id: int,
    body: OrganizationFields,
    _role: str = Depends(require_jwt_admin),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    """Change the fields sent; leave every other field alone."""
    fields = clean_fields(body, TEXT_LIMITS, require_name=False)
    if not fields and body.do_not_contact is None:
        raise HTTPException(status_code=400, detail="Nothing to change")
    _, workspace_id = _personal_identity(payload)
    scope = "AND workspace_id = %s" if workspace_id is not None else ""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT city, country, name FROM contacts WHERE id = %s AND deleted_at IS NULL {scope}",
            [contact_id] + ([workspace_id] if workspace_id is not None else []),
        )
        current = cur.fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="Contact not found")

    writes = dict(fields)
    moved = ("city" in fields and (fields["city"] or "") != (current["city"] or "")) or (
        "country" in fields and (fields["country"] or "") != (current["country"] or "")
    )
    if moved:
        # Never leave the old place's position on the new place; better none.
        new_city = fields.get("city", current["city"]) or ""
        new_country = fields.get("country", current["country"]) or "DE"
        coords = geocode(new_city, new_country) if new_city else None
        writes["latitude"], writes["longitude"] = coords if coords else (None, None)
    if writes:
        _write_columns(contact_id, writes, workspace_id)
    if body.do_not_contact is not None:
        set_suppression_flag(contact_id, "do_not_contact", bool(body.do_not_contact))
    log_audit(None, None, "contact.edited", f"contact:{contact_id}", ",".join(sorted(fields)) or "flags")
    return {"id": contact_id, "changed": sorted(fields)}
