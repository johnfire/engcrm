import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.config import MAX_UPLOAD_BYTES
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_people import get_person, save_person, update_person
from gcrm.tools.db_people_interactions import (
    delete_person_interaction,
    get_person_interactions,
    log_person_note,
)
from gcrm.tools.email_extract import extract_person_from_email
from gcrm.tools.transcribe import transcribe

logger = logging.getLogger(__name__)

# What the browser is told when transcription fails. Deliberately free of
# detail — the diagnosable version is in the server log.
_TRANSCRIBE_FAILED = "Couldn't make out any speech — try again or type your note."

router = APIRouter(dependencies=[Depends(require_login)])

# Whitelisted so `sort` can be trusted straight into an f-string ORDER BY below.
SORT_COLUMNS = {
    "created_at": "created_at",
    "name":       "lower(name)",
}


@router.get("/people/", response_class=HTMLResponse)
def people_list(
    request: Request,
    q: str = "",
    sort: str = Query(default="created_at"),
    dir: str = Query(default="desc"),
):
    sort_col = SORT_COLUMNS.get(sort, SORT_COLUMNS["created_at"])
    sort_dir = "DESC" if dir == "desc" else "ASC"
    with db() as conn:
        cur = conn.cursor()
        if q:
            cur.execute(
                f"""
                SELECT * FROM people
                WHERE name ILIKE %s OR email ILIKE %s OR city ILIKE %s
                ORDER BY {sort_col} {sort_dir}
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            )
        else:
            cur.execute(f"SELECT * FROM people ORDER BY {sort_col} {sort_dir}")
        people = [dict(row) for row in cur.fetchall()]

    return templates.TemplateResponse("people.html", {
        "request": request,
        "people": people,
        "query": q,
        "sort": sort,
        "dir": dir,
    })


@router.post("/people/extract-email")
def extract_email(body: dict = Body(...), _admin: str = Depends(require_admin)) -> dict:
    """Best-effort extraction, no DB write — the confirm form is the save step."""
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No email text provided")
    result = extract_person_from_email(text)
    return {"fields": result["fields"]}


@router.get("/people/new", response_class=HTMLResponse)
def person_new(request: Request):
    return templates.TemplateResponse("person_new.html", {"request": request})


@router.post("/people/new")
def person_create(
    name: str = Form(""),
    title: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    relationship: str = Form(""),
    met_at: str = Form(""),
    notes: str = Form(""),
    _admin: str = Depends(require_admin),
):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    person_id = save_person(
        name=name.strip(), title=title.strip(), email=email.strip(), phone=phone.strip(),
        website=website.strip(), city=city.strip(), country=country.strip(),
        relationship=relationship.strip(), notes=notes.strip(), met_at=met_at.strip(),
        source="manual",
    )
    log_audit(None, None, "person.created", f"person:{person_id}", "created")
    return local_redirect(f"/people/{person_id}", saved="1")


@router.get("/people/{person_id}", response_class=HTMLResponse)
def person_detail(
    request: Request,
    person_id: int,
    saved: bool = Query(default=False),
):
    person = get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return templates.TemplateResponse("person_detail.html", {
        "request": request,
        "person": person,
        "saved": saved,
        "interactions": get_person_interactions(person_id),
    })


@router.post("/people/{person_id}/edit")
def person_edit(
    person_id: int,
    name: str = Form(""),
    title: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    relationship: str = Form(""),
    met_at: str = Form(""),
    notes: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Save the edited person. Name is the one field the row cannot lose."""
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    updated = update_person(person_id, {
        "name": name, "title": title, "email": email, "phone": phone,
        "website": website, "city": city, "country": country,
        "relationship": relationship, "met_at": met_at, "notes": notes,
    })
    if not updated:
        raise HTTPException(status_code=404, detail="Person not found")
    log_audit(None, None, "person.edited", f"person:{person_id}", "updated")
    return local_redirect(f"/people/{person_id}", saved="1")


@router.post("/people/{person_id}/notes/transcribe")
def transcribe_note(
    person_id: int,
    audio: UploadFile = File(...),
    _admin: str = Depends(require_admin),
) -> dict:
    """Transcribe a recorded note for review — no DB write. The Save button is the write."""
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    audio_bytes = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large")
    try:
        transcript = transcribe(audio_bytes, audio.filename or "note.webm")
    except Exception:
        logger.exception("person note transcription failed")
        raise HTTPException(status_code=502, detail="Transcription service unavailable")
    if not transcript:
        raise HTTPException(status_code=422, detail=_TRANSCRIBE_FAILED)
    return {"transcript": transcript}


@router.post("/people/{person_id}/notes")
def add_note(
    person_id: int,
    note: str = Form(""),
    method: str = Form(""),
    _admin: str = Depends(require_admin),
):
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    if not note.strip():
        raise HTTPException(status_code=400, detail="Note is required")
    log_person_note(person_id, method.strip() or None, note.strip())
    return local_redirect(f"/people/{person_id}", saved="1")


@router.post("/people/{person_id}/notes/{note_id}/delete")
def remove_note(person_id: int, note_id: int, _admin: str = Depends(require_admin)):
    if not delete_person_interaction(person_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return local_redirect(f"/people/{person_id}", saved="1")
