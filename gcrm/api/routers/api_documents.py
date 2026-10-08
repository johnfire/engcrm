"""Photographed pages become separate, editable drafts in the capture queue."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from psycopg2.extras import Json

from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.api.routers.api_capture_linkedin import establish_capture_workspace
from gcrm.audit_context import audit_scope, current_audit_context
from gcrm.config import MAX_UPLOAD_BYTES
from gcrm.db.connection import db
from gcrm.tools import cards, documents
from gcrm.tools.db_audit import log_audit
from gcrm.workspace_context import get_workspace_id

router = APIRouter(prefix="/api/documents", tags=["mobile-documents"])


def read_document_upload(image: UploadFile) -> bytes:
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(415, "Expected an image upload")
    image_bytes = image.file.read(MAX_UPLOAD_BYTES + 1)
    if not image_bytes:
        raise HTTPException(400, "Empty image")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image too large")
    return image_bytes


def find_batch_captures(cursor, batch_id: str) -> list[dict]:
    cursor.execute(
        "SELECT id AS capture_id, extracted AS fields, confidence "
        "FROM card_captures WHERE capture_batch_id=%s AND kind='document' "
        "ORDER BY document_row", (batch_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def stage_document_row(cursor, batch_id, row_number, fields, extraction, image_bytes) -> dict:
    context = current_audit_context()
    cursor.execute(
        "INSERT INTO card_captures (captured_by, kind, capture_batch_id, document_row, "
        "extracted, confidence, extraction_model, extraction_cost_usd, extraction_status, workspace_id) "
        "VALUES (%s, 'document', %s, %s, %s, %s, %s, %s, 'done', "
        "COALESCE(%s, (SELECT id FROM workspaces WHERE slug='default'))) RETURNING id",
        (context.actor if context else "shared-admin", batch_id, row_number, Json(fields),
         fields.get("confidence"), extraction["model"], extraction["cost_usd"] if row_number == 0 else 0,
         get_workspace_id()),
    )
    capture_id = cursor.fetchone()["id"]
    image_path = cards.save_card_image(capture_id, image_bytes)
    try:
        duplicate = cards.find_possible_duplicate(fields)
        cursor.execute("UPDATE card_captures SET image_path=%s, dup_contact_id=%s WHERE id=%s",
                       (image_path, duplicate["id"] if duplicate else None, capture_id))
    except Exception:
        cards.delete_card_image(image_path)
        raise
    return {"capture_id": capture_id, "fields": fields, "confidence": fields.get("confidence")}


def persist_document_drafts(batch_id, extraction, image_bytes) -> list[dict]:
    created_captures = []
    try:
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (batch_id,))
            existing = find_batch_captures(cursor, batch_id)
            if existing:
                return existing
            for row_number, fields in enumerate(extraction["contacts"]):
                created_captures.append(stage_document_row(
                    cursor, batch_id, row_number, fields, extraction, image_bytes,
                ))
    except Exception:
        for capture in created_captures:
            cards.delete_card_image(f"{capture['capture_id']}.jpg")
        raise
    for capture in created_captures:
        log_audit(None, None, "document.captured", f"card_capture:{capture['capture_id']}", "pending_review")
    return created_captures


@router.post("")
def capture_document(
    request: Request,
    image: UploadFile = File(...),
    capture_batch_id: str = Form(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$"),
    _role: str = Depends(require_jwt_admin),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    # Sync dependencies run in separate thread contexts; establish the actor here.
    establish_capture_workspace(payload)
    actor = f"user:{payload['uid']}" if payload.get("uid") is not None else "shared-admin"
    with audit_scope(actor, "user", request.state.correlation_id):
        return create_document_drafts(image, capture_batch_id)


def create_document_drafts(image: UploadFile, capture_batch_id: str) -> dict:
    image_bytes = read_document_upload(image)
    with db() as connection:
        existing = find_batch_captures(connection.cursor(), capture_batch_id)
    if existing:
        return {"is_document": True, "captures": existing, "note": None}
    context = current_audit_context()
    with audit_scope("agent:document_vision", "ai", context.correlation_id if context else None):
        extraction = documents.extract_document_contacts(image_bytes, image.content_type or "image/jpeg")
        log_audit(None, None, "document.extracted", f"capture_batch:{capture_batch_id}",
                  f"contacts:{len(extraction['contacts'])}")
    if not extraction["contacts"]:
        return {"is_document": False, "captures": [], "note": extraction.get("note") or documents.EXTRACTION_FAILED}
    captures = persist_document_drafts(capture_batch_id, extraction, image_bytes)
    return {"is_document": True, "captures": captures, "note": extraction.get("note")}
