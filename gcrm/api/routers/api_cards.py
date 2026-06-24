"""Mobile business-card capture endpoints (JSON + multipart image upload).

Flow: POST a card photo -> stored on the VPS volume + Claude-vision extraction +
dedup check -> the app shows an editable confirm screen -> POST .../confirm
promotes it to a contact and kicks enrichment in the background.
"""
import logging

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel
from psycopg2.extras import Json

from gcrm.api.jwt_auth import require_jwt, require_jwt_admin
from gcrm.config import CARD_IMAGE_RETENTION_DAYS, MAX_UPLOAD_BYTES
from gcrm.db.connection import db
from gcrm.tools import cards
from gcrm.tools.db import serialize_row

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cards", tags=["mobile-cards"])


def _as_int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) else None


@router.post("")
def capture_card(
    image: UploadFile = File(...),
    gps_lat: float | None = Form(None),
    gps_lng: float | None = Form(None),
    role: str = Depends(require_jwt_admin),
) -> dict:
    """Store the photo, extract fields with Claude vision, return fields + any
    likely duplicate for the confirm screen."""
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
            "INSERT INTO card_captures (captured_by, gps_lat, gps_lng) VALUES (%s, %s, %s) RETURNING id",
            (role, gps_lat, gps_lng),
        )
        capture_id = cur.fetchone()["id"]

    image_path = cards.save_card_image(capture_id, image_bytes)
    result = cards.extract_card_fields(image_bytes, image.content_type or "image/jpeg")
    fields = result["fields"]
    is_card = bool(fields.get("is_card"))
    dup = cards.find_possible_duplicate(fields) if is_card else None

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE card_captures
               SET image_path=%s, extracted=%s, extraction_model=%s, extraction_cost_usd=%s,
                   confidence=%s, extraction_status=%s, dup_contact_id=%s, error=%s, updated_at=NOW()
             WHERE id=%s
            """,
            (
                image_path, Json(fields), result["model"], result["cost_usd"],
                _as_int(fields.get("confidence")),
                "done" if is_card else "failed",
                dup["id"] if dup else None,
                fields.get("error"),
                capture_id,
            ),
        )

    return {
        "capture_id": capture_id,
        "is_card": is_card,
        "confidence": fields.get("confidence"),
        "fields": fields,
        "dup_suggestion": dup,
        "cost_usd": result["cost_usd"],
    }


@router.get("")
def list_captures(status: str = "pending_review", _role: str = Depends(require_jwt)) -> list[dict]:
    """Pending (or other-status) captures — powers the review/batch queue."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, captured_at, status, extraction_status, confidence,
                      extracted, dup_contact_id, contact_id
                 FROM card_captures WHERE status=%s
                 ORDER BY captured_at DESC LIMIT 100""",
            (status,),
        )
        rows = cur.fetchall()
    return [serialize_row(dict(r)) for r in rows]


@router.get("/{capture_id}/image")
def get_capture_image(capture_id: int, _role: str = Depends(require_jwt)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM card_captures WHERE id=%s", (capture_id,))
        row = cur.fetchone()
    if not row or not row["image_path"]:
        raise HTTPException(status_code=404, detail="No image")
    data = cards.read_card_image(row["image_path"])
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/jpeg")


class ConfirmBody(BaseModel):
    fields: dict
    link_to_contact_id: int | None = None


@router.post("/{capture_id}/confirm")
def confirm_capture(
    capture_id: int,
    body: ConfirmBody,
    background: BackgroundTasks,
    _role: str = Depends(require_jwt_admin),
) -> dict:
    """Promote the (edited) fields to a contact, then enrich in the background."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, status, image_path FROM card_captures WHERE id=%s", (capture_id,))
        cap = cur.fetchone()
    if not cap:
        raise HTTPException(status_code=404, detail="Capture not found")
    if cap["status"] == "confirmed":
        raise HTTPException(status_code=409, detail="Already confirmed")

    if body.link_to_contact_id:
        contact_id = body.link_to_contact_id
    else:
        contact_id = cards.promote_to_contact(body.fields)
        if contact_id == 0:  # save_contact deduped — link to the existing match
            dup = cards.find_possible_duplicate(body.fields)
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

    background.add_task(cards.enrich_one, contact_id)
    return {"contact_id": contact_id, "capture_id": capture_id}


@router.post("/{capture_id}/discard")
def discard_capture(capture_id: int, _role: str = Depends(require_jwt_admin)) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM card_captures WHERE id=%s", (capture_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Capture not found")
        cur.execute("UPDATE card_captures SET status='discarded', updated_at=NOW() WHERE id=%s", (capture_id,))
    cards.delete_card_image(row["image_path"])
    return {"ok": True}
