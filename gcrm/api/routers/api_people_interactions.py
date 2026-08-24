"""Mobile JSON API for the per-person note log — record, transcribe, save,
list, delete. Mirrors the web routes in people.py; both share
db_people_interactions.py and the same Whisper transcription pipeline as the
organization voice-memo flow (api_voice.py)."""
import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_admin
from gcrm.config import MAX_UPLOAD_BYTES
from gcrm.tools.db_people import get_person
from gcrm.tools.db_people_interactions import (
    delete_person_interaction,
    get_person_interactions,
    log_person_note,
)
from gcrm.tools.transcribe import transcribe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/people", tags=["mobile-people-interactions"])


@router.get("/{person_id}/notes")
def list_notes(person_id: int, _role: str = Depends(require_jwt)) -> list[dict]:
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return get_person_interactions(person_id)


@router.post("/{person_id}/notes/transcribe")
def transcribe_note(
    person_id: int,
    audio: UploadFile = File(...),
    _role: str = Depends(require_jwt_admin),
) -> dict:
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    audio_bytes = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large")
    safe_name = os.path.basename(audio.filename or "note.m4a")
    try:
        transcript = transcribe(audio_bytes, safe_name)
    except Exception:
        logger.exception("person note transcription failed")
        raise HTTPException(status_code=502, detail="Transcription service unavailable")
    if not transcript:
        raise HTTPException(status_code=422, detail="Couldn't make out any speech — try again.")
    return {"transcript": transcript}


class NoteBody(BaseModel):
    note: str
    method: str | None = None


@router.post("/{person_id}/notes")
def add_note(person_id: int, body: NoteBody, _role: str = Depends(require_jwt_admin)) -> dict:
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="Note is required")
    note_id = log_person_note(person_id, (body.method or "").strip() or None, note)
    return {"id": note_id}


@router.delete("/{person_id}/notes/{note_id}")
def remove_note(person_id: int, note_id: int, _role: str = Depends(require_jwt_admin)) -> None:
    if not delete_person_interaction(person_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
