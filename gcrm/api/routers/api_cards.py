"""Mobile business-card capture endpoints (JSON + multipart image upload).

Flow: POST a card photo -> stored on the VPS volume + Claude-vision extraction +
dedup check -> the app shows an editable confirm screen -> POST .../confirm
promotes it to a contact and kicks enrichment in the background.
"""
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from psycopg2.extras import Json
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_admin, require_jwt_payload
from gcrm.audit_context import audit_scope, current_audit_context
from gcrm.config import CARD_IMAGE_RETENTION_DAYS, MAX_UPLOAD_BYTES
from gcrm.db.connection import db
from gcrm.tools import cards
from gcrm.tools.db import serialize_row
from gcrm.tools.db_audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cards", tags=["mobile-cards"])


def _as_int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) else None


@router.post("")
def capture_card(
    request: Request,
    image: UploadFile = File(...),
    gps_lat: float | None = Form(None),
    gps_lng: float | None = Form(None),
    role: str = Depends(require_jwt_admin),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    """Accept a card or primary document contact through existing mobile clients."""
    actor = f"user:{payload['uid']}" if payload.get("uid") is not None else "shared-admin"
    with audit_scope(actor, "user", request.state.correlation_id):
        return create_contact_capture(image, gps_lat, gps_lng, actor)


def create_contact_capture(image: UploadFile, gps_lat, gps_lng, actor: str) -> dict:
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Expected an image upload")
    image_bytes = image.file.read(MAX_UPLOAD_BYTES + 1)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO card_captures (captured_by, gps_lat, gps_lng) VALUES (%s, %s, %s) RETURNING id",
            (actor, gps_lat, gps_lng),
        )
        capture_id = cursor.fetchone()["id"]
    image_path = cards.save_card_image(capture_id, image_bytes)
    context = current_audit_context()
    with audit_scope("agent:contact_vision", "ai", context.correlation_id if context else None):
        extraction = cards.extract_card_fields(image_bytes, image.content_type or "image/jpeg")
        log_audit(None, None, "card.extracted", f"card_capture:{capture_id}",
                  "extracted" if extraction["fields"].get("is_card") else "failed")
    fields = extraction["fields"]
    is_card = bool(fields.get("is_card"))
    duplicate = cards.find_possible_duplicate(fields) if is_card else None
    store_capture_extraction(capture_id, image_path, extraction, duplicate)
    log_audit(None, None, "card.captured", f"card_capture:{capture_id}", "pending_review")
    return {
        "capture_id": capture_id, "is_card": is_card, "confidence": fields.get("confidence"),
        "fields": fields, "dup_suggestion": duplicate, "cost_usd": extraction["cost_usd"],
    }


def store_capture_extraction(capture_id: int, image_path: str, extraction: dict, duplicate: dict | None) -> None:
    fields = extraction["fields"]
    kind = "document" if fields.get("kind") == "document" else "card"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE card_captures
               SET kind=%s, image_path=%s, extracted=%s, extraction_model=%s, extraction_cost_usd=%s,
                   confidence=%s, extraction_status=%s, dup_contact_id=%s, error=%s, updated_at=NOW()
             WHERE id=%s
            """,
            (
                kind, image_path, Json(fields), extraction["model"], extraction["cost_usd"],
                _as_int(fields.get("confidence")), "done" if fields.get("is_card") else "failed",
                duplicate["id"] if duplicate else None, fields.get("error"), capture_id,
            ),
        )


@router.get("")
def list_captures(status: str = "pending_review", _role: str = Depends(require_jwt)) -> list[dict]:
    """Pending (or other-status) captures — powers the review/batch queue."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT capture.id, capture.kind, capture.captured_at, capture.status,
                      capture.extraction_status, capture.confidence, capture.extracted,
                      capture.dup_contact_id, capture.contact_id, capture.place_json,
                      CASE WHEN duplicate.id IS NOT NULL THEN json_build_object(
                          'id', duplicate.id, 'name', duplicate.name, 'city', duplicate.city,
                          'email', duplicate.email, 'phone', duplicate.phone
                      ) END AS dup_suggestion
                 FROM card_captures capture
                 LEFT JOIN contacts duplicate ON duplicate.id=capture.dup_contact_id AND duplicate.deleted_at IS NULL
                WHERE capture.status=%s
                 ORDER BY capture.captured_at DESC, capture.id ASC LIMIT 100""",
            (status,),
        )
        rows = cur.fetchall()
    return [serialize_row(dict(row)) for row in rows]


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


def promote_confirmed_organization(body: ConfirmBody, source: str) -> int:
    if body.link_to_contact_id:
        return body.link_to_contact_id
    contact_id = (cards.promote_to_organization(body.fields, source=source)
                  if source == "document_capture" else cards.promote_to_organization(body.fields))
    if contact_id:
        return contact_id
    duplicate = cards.find_possible_duplicate(body.fields)
    if not duplicate:
        raise HTTPException(status_code=409, detail="Duplicate contact, no match resolved")
    return duplicate["id"]


def record_confirmed_person(fields: dict, contact_id: int, source: str) -> int:
    try:
        return (cards.promote_to_person(fields, contact_id, source=source)
                if source == "document_capture" else cards.promote_to_person(fields, contact_id))
    except Exception:
        logger.exception("capture person creation failed for contact %s", contact_id)
        if source == "document_capture":
            raise HTTPException(503, "Could not save the person. This draft is still pending; please retry.")
        return 0


def save_reviewed_capture(capture_id: int, body: ConfirmBody) -> tuple[dict, int, int]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, kind, status, image_path FROM card_captures "
            "WHERE id=%s AND kind IN ('card', 'document') FOR UPDATE", (capture_id,),
        )
        capture = cursor.fetchone()
        if not capture:
            raise HTTPException(404, "Capture not found")
        if capture["status"] != "pending_review":
            raise HTTPException(409, "Capture is no longer pending review")
        if not (body.fields.get("company") or body.fields.get("name") or "").strip():
            raise HTTPException(400, "Company or person name is required")
        source = "document_capture" if capture.get("kind") == "document" else "card_capture"
        contact_id = promote_confirmed_organization(body, source)
        person_id = record_confirmed_person(body.fields, contact_id, source)
        cursor.execute(
            "UPDATE card_captures SET status='confirmed', contact_id=%s, extracted=%s, updated_at=NOW() WHERE id=%s",
            (contact_id, Json(body.fields), capture_id),
        )
    return capture, contact_id, person_id


def enrich_document_contact(contact_id: int, correlation_id: str | None) -> None:
    with audit_scope("agent:enrichment_agent", "ai", correlation_id):
        cards.enrich_one(contact_id)


def complete_reviewed_capture(capture_id: int, body: ConfirmBody, background: BackgroundTasks) -> dict:
    capture, contact_id, person_id = save_reviewed_capture(capture_id, body)
    if CARD_IMAGE_RETENTION_DAYS <= 0 and capture["image_path"]:
        cards.delete_card_image(capture["image_path"])
    if capture.get("kind") == "document":
        context = current_audit_context()
        background.add_task(enrich_document_contact, contact_id, context.correlation_id if context else None)
    else:
        background.add_task(cards.enrich_one, contact_id)
    log_audit(None, None, "card.confirmed", f"card_capture:{capture_id}", f"contact:{contact_id}")
    return {"contact_id": contact_id, "capture_id": capture_id, "person_id": person_id or None}


@router.post("/{capture_id}/confirm")
def confirm_capture(
    capture_id: int,
    body: ConfirmBody,
    background: BackgroundTasks,
    request: Request,
    _role: str = Depends(require_jwt_admin),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    """Save a reviewed card or document row, then enrich its organization."""
    actor = f"user:{payload['uid']}" if payload.get("uid") is not None else "shared-admin"
    with audit_scope(actor, "user", request.state.correlation_id):
        return complete_reviewed_capture(capture_id, body, background)


@router.post("/{capture_id}/discard")
def discard_capture(capture_id: int, _role: str = Depends(require_jwt_admin)) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM card_captures WHERE id=%s AND kind IN ('card', 'document')", (capture_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Capture not found")
        cur.execute("UPDATE card_captures SET status='discarded', updated_at=NOW() WHERE id=%s", (capture_id,))
    cards.delete_card_image(row["image_path"])
    log_audit(None, None, "card.discarded", f"card_capture:{capture_id}", "discarded")
    return {"ok": True}
