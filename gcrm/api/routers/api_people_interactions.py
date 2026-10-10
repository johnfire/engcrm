"""Mobile JSON API for the per-person note log — record, transcribe, save,
list, delete. Mirrors the web routes in people.py; both share
db_people_interactions.py and the same Whisper transcription pipeline as the
organization voice-memo flow (api_voice.py)."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from gcrm.activity_types import PERSON_METHODS, parse_minutes
from gcrm.api.jwt_auth import require_jwt, require_jwt_admin
from gcrm.api.transcribe_upload import transcribe_upload
from gcrm.tools.db_people import get_person
from gcrm.tools.db_people_interactions import (
    delete_person_interaction,
    get_person_interactions,
    log_person_note,
)
from gcrm.tools.deal_records import resolve_log_offer

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
    transcript = transcribe_upload(audio)
    return {"transcript": transcript}


class NoteBody(BaseModel):
    note: str
    method: str | None = None
    duration_minutes: int | None = None  # how long it took; blank uses the type's default
    offer: str | None = None  # the offer's slug, "general", or absent: picked from the open deals


@router.post("/{person_id}/notes")
def add_note(person_id: int, body: NoteBody, _role: str = Depends(require_jwt_admin)) -> dict:
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="Note is required")
    method = (body.method or "").strip() or None
    if method is not None and method not in PERSON_METHODS:
        raise HTTPException(status_code=400, detail="Unknown method")
    try:
        minutes = parse_minutes(body.duration_minutes)
    except ValueError:
        raise HTTPException(status_code=400, detail="duration_minutes must be 0..1440")
    try:
        offer_id = resolve_log_offer("person", person_id, body.offer)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown offer")
    note_id = log_person_note(person_id, method, note, duration_minutes=minutes, offer_id=offer_id)
    return {"id": note_id}


@router.delete("/{person_id}/notes/{note_id}")
def remove_note(person_id: int, note_id: int, _role: str = Depends(require_jwt_admin)) -> None:
    if not delete_person_interaction(person_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
