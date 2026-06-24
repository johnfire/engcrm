"""Mobile voice-memo capture: audio -> Whisper transcript -> structured CRM action.

POST /api/voice          multipart audio -> transcript + summary + candidate
                         contacts + follow-up (for the confirm screen)
POST /api/voice/confirm  apply: log the interaction on the chosen/new contact,
                         with an optional follow-up date
"""
import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin
from gcrm.config import MAX_UPLOAD_BYTES
from gcrm.tools.transcribe import transcribe
from gcrm.tools.voice import structure_transcript
from gcrm.tools.db import search_contacts_by_name, log_voice_interaction, save_contact

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["mobile-voice"])


def _valid_iso_date(s: str | None) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return None


@router.post("")
def process_voice(
    audio: UploadFile = File(...),
    language: str = Form(""),
    _role: str = Depends(require_jwt_admin),
) -> dict:
    audio_bytes = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large")
    safe_name = os.path.basename(audio.filename or "memo.m4a")
    try:
        transcript = transcribe(audio_bytes, safe_name, language or None)
    except Exception:
        logger.exception("transcription failed")
        raise HTTPException(status_code=502, detail="Transcription service unavailable")
    if not transcript:
        raise HTTPException(status_code=422, detail="Couldn't make out any speech — try again.")

    structured = structure_transcript(transcript, date.today().isoformat())
    candidates = search_contacts_by_name(structured.get("contact_query") or "")
    return {
        "transcript": transcript,
        "summary": structured.get("summary") or transcript,
        "contact_query": structured.get("contact_query"),
        "follow_up_date": _valid_iso_date(structured.get("follow_up_date")),
        "follow_up_text": structured.get("follow_up_text"),
        "is_new_lead": bool(structured.get("is_new_lead")),
        "candidates": candidates,
    }


class VoiceConfirm(BaseModel):
    contact_id: int | None = None
    new_contact_name: str | None = None
    summary: str
    follow_up_date: str | None = None
    follow_up_text: str | None = None


@router.post("/confirm")
def confirm_voice(body: VoiceConfirm, _role: str = Depends(require_jwt_admin)) -> dict:
    contact_id = body.contact_id
    if not contact_id:
        name = (body.new_contact_name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Pick a contact or give a new name.")
        contact_id = save_contact(name=name, city="", status="candidate")
        if contact_id == 0:  # save_contact deduped — link to the existing match
            match = search_contacts_by_name(name, limit=1)
            if not match:
                raise HTTPException(status_code=409, detail="Duplicate contact, no match resolved.")
            contact_id = match[0]["id"]

    fu_date = _valid_iso_date(body.follow_up_date)
    log_voice_interaction(
        contact_id,
        body.summary.strip(),
        outcome="follow_up_needed" if fu_date else None,
        next_action=(body.follow_up_text or "").strip() or None,
        next_action_date=fu_date,
    )
    return {"contact_id": contact_id}
