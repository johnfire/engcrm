"""Mobile storefront-sign capture endpoints (JSON + multipart image upload).

Flow: POST a sign photo -> stored on the VPS volume + Claude-vision extraction
of the business name + a Google Places resolution attempt (using GPS) -> the
app shows a confirm screen where the user can edit the name and accept/reject
the resolved Place -> POST .../confirm promotes it to a contact and kicks off
background research (enrichment agent + key-people lookup) via signs.research_business.

Shares the card_captures table with business cards (kind='sign') — see
migration 034_sign_capture_kind.sql — and reuses cards.save_card_image /
find_possible_duplicate / promote_to_contact / delete_card_image throughout.
"""
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from psycopg2.extras import Json
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin
from gcrm.config import CARD_IMAGE_RETENTION_DAYS, MAX_UPLOAD_BYTES
from gcrm.db.connection import db
from gcrm.tools import cards, signs
from gcrm.tools.db_audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signs", tags=["mobile-signs"])


def _as_int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) else None


@router.post("")
def capture_sign(
    image: UploadFile = File(...),
    gps_lat: float | None = Form(None),
    gps_lng: float | None = Form(None),
    role: str = Depends(require_jwt_admin),
) -> dict:
    """Store the photo, extract the business name with Claude vision, try to
    resolve it to a Google Place, and return everything for the confirm screen."""
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Expected an image upload")
    image_bytes = image.file.read(MAX_UPLOAD_BYTES + 1)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO card_captures (captured_by, gps_lat, gps_lng, kind) "
            "VALUES (%s, %s, %s, 'sign') RETURNING id",
            (role, gps_lat, gps_lng),
        )
        capture_id = cur.fetchone()["id"]

    image_path = cards.save_card_image(capture_id, image_bytes)
    result = signs.extract_sign_fields(image_bytes, image.content_type or "image/jpeg")
    fields = result["fields"]
    is_sign = bool(fields.get("is_sign"))

    gps = (gps_lat, gps_lng) if gps_lat is not None and gps_lng is not None else None
    place = signs.resolve_business(fields.get("business_name", ""), gps) if is_sign else None
    dup = (
        cards.find_possible_duplicate({
            "company": (place or {}).get("name") or fields.get("business_name"),
            "phone": fields.get("phone"),
        })
        if is_sign
        else None
    )

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE card_captures
               SET image_path=%s, extracted=%s, extraction_model=%s, extraction_cost_usd=%s,
                   confidence=%s, extraction_status=%s, dup_contact_id=%s, error=%s,
                   place_id=%s, place_json=%s, updated_at=NOW()
             WHERE id=%s
            """,
            (
                image_path, Json(fields), result["model"], result["cost_usd"],
                _as_int(fields.get("confidence")),
                "done" if is_sign else "failed",
                dup["id"] if dup else None,
                fields.get("error"),
                place.get("place_id") if place else None,
                Json(place) if place else None,
                capture_id,
            ),
        )
    log_audit(None, None, "sign.captured", f"card_capture:{capture_id}", "extracted")

    return {
        "capture_id": capture_id,
        "is_sign": is_sign,
        "confidence": fields.get("confidence"),
        "fields": fields,
        "place": place,
        "dup_suggestion": dup,
        "cost_usd": result["cost_usd"],
    }


class ConfirmSignBody(BaseModel):
    business_name: str
    accept_place: bool = False
    link_to_contact_id: int | None = None


@router.post("/{capture_id}/confirm")
def confirm_sign(
    capture_id: int,
    body: ConfirmSignBody,
    background: BackgroundTasks,
    _role: str = Depends(require_jwt_admin),
) -> dict:
    """Promote the confirmed business to a contact, then research it in the background."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, image_path, extracted, place_json "
            "FROM card_captures WHERE id=%s AND kind='sign'",
            (capture_id,),
        )
        cap = cur.fetchone()
    if not cap:
        raise HTTPException(status_code=404, detail="Capture not found")
    if cap["status"] == "confirmed":
        raise HTTPException(status_code=409, detail="Already confirmed")

    name = body.business_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="business_name is required")

    if body.link_to_contact_id:
        contact_id = body.link_to_contact_id
    else:
        place = cap["place_json"] if body.accept_place else None
        contact_fields = signs.build_contact_fields(name, cap["extracted"] or {}, place)
        contact_id = cards.promote_to_contact(contact_fields, source="sign_scan")
        if contact_id == 0:  # save_contact deduped — link to the existing match
            dup = cards.find_possible_duplicate(contact_fields)
            if not dup:
                raise HTTPException(status_code=409, detail="Duplicate contact, no match resolved")
            contact_id = dup["id"]

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE card_captures SET status='confirmed', contact_id=%s, updated_at=NOW() WHERE id=%s",
            (contact_id, capture_id),
        )

    if CARD_IMAGE_RETENTION_DAYS <= 0 and cap["image_path"]:
        cards.delete_card_image(cap["image_path"])

    background.add_task(signs.research_business, contact_id)
    log_audit(None, None, "sign.confirmed", f"card_capture:{capture_id}", f"contact:{contact_id}")
    return {"contact_id": contact_id, "capture_id": capture_id}


@router.post("/{capture_id}/discard")
def discard_sign(capture_id: int, _role: str = Depends(require_jwt_admin)) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM card_captures WHERE id=%s AND kind='sign'", (capture_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Capture not found")
        cur.execute("UPDATE card_captures SET status='discarded', updated_at=NOW() WHERE id=%s", (capture_id,))
    cards.delete_card_image(row["image_path"])
    log_audit(None, None, "sign.discarded", f"card_capture:{capture_id}", "discarded")
    return {"ok": True}
