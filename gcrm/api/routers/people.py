import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.config import MAIL_SENDER_OPTIONS, MAX_UPLOAD_BYTES
from gcrm.tools.curiosity_email import draft_curiosity_email
from gcrm.tools.db_approvals import queue_person_draft
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_people import (
    get_people,
    get_person,
    save_person,
    set_person_value_rating,
    update_person,
)
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


class PersonValueRatingBody(BaseModel):
    priority: int | None = None


@router.get("/people/", response_class=HTMLResponse)
def people_list(
    request: Request,
    q: str = "",
    sort: str = Query(default="created_at"),
    dir: str = Query(default="desc"),
):
    people = get_people(q, sort, dir, request.session.get("user_id"))
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
    person = get_person(person_id, request.session.get("user_id"))
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return templates.TemplateResponse("person_detail.html", {
        "request": request,
        "person": person,
        "saved": saved,
        "interactions": get_person_interactions(person_id),
        "mail_sender_options": MAIL_SENDER_OPTIONS,
    })


@router.put("/people/{person_id}/value-rating")
def update_person_value_rating(
    person_id: int,
    body: PersonValueRatingBody,
    request: Request,
):
    """Set or clear the signed-in user's private value-as-a-contact rating for one person."""
    user_id = request.session.get("user_id")
    workspace_id = request.session.get("workspace_id")
    if user_id is None or workspace_id is None:
        raise HTTPException(status_code=403, detail="Personal account required")
    if body.priority is not None and body.priority not in range(1, 6):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    person_found, stored_rating = set_person_value_rating(
        user_id, workspace_id, person_id, body.priority,
    )
    if not person_found:
        raise HTTPException(status_code=404, detail="Person not found")

    outcome = "cleared" if stored_rating is None else f"set:{stored_rating}"
    log_audit(None, None, "person.value_rating_changed", f"person:{person_id}", outcome)
    return {"value_rating": stored_rating}


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


@router.post("/people/{person_id}/curiosity-email/draft")
def draft_curiosity_email_route(
    person_id: int,
    language: str = Query(default="en"),
    from_email: str = Query(default=""),
    _admin: str = Depends(require_admin),
) -> dict:
    """Generates the email and immediately queues it as a held draft — review
    and sending happen on the Drafts page, not here. See
    docs/plans/2026-08-26-person-curiosity-email-design.md."""
    if language not in ("en", "de"):
        language = "en"
    sender = from_email if from_email in MAIL_SENDER_OPTIONS else None
    try:
        result = draft_curiosity_email(person_id, language)
    except LookupError:
        raise HTTPException(status_code=404, detail="Person not found")
    if "error" in result:
        return result
    draft_id = queue_person_draft(person_id, result["subject"], result["body"], sender)
    log_audit(None, None, "person.curiosity_email_drafted", f"person:{person_id}", f"draft:{draft_id}")
    return {"draft_id": draft_id}
