import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.config import MAIL_SENDER_OPTIONS, MAX_UPLOAD_BYTES, PEOPLE_RETENTION_DAYS
from gcrm.linkedin import decode_export, parse_connections_csv
from gcrm.tools.curiosity_email import draft_curiosity_email
from gcrm.tools.db_approvals import queue_person_draft
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_linkedin import (
    CITY_QUEUE_PAGE_SIZE,
    apply_city_decisions,
    apply_match_decisions,
    get_city_review_queue,
    get_match_suggestions,
    import_connections,
)
from gcrm.tools.db_people import (
    get_people,
    get_person,
    save_person,
    search_organizations,
    set_person_organization,
    set_person_value_rating,
    update_person,
)
from gcrm.tools.db_people_interactions import (
    delete_person_interaction,
    get_person_interactions,
    log_person_note,
)
from gcrm.tools.email_extract import extract_person_from_email
from gcrm.tools.privacy_retention import erase_person
from gcrm.tools.transcribe import transcribe

logger = logging.getLogger(__name__)

# What the browser is told when transcription fails. Deliberately free of
# detail — the diagnosable version is in the server log.
_TRANSCRIBE_FAILED = "Couldn't make out any speech — try again or type your note."

router = APIRouter(dependencies=[Depends(require_login)])

# Rows per page on the LinkedIn match-review screen.
MATCH_PAGE_SIZE = 100


class PersonValueRatingBody(BaseModel):
    priority: int | None = None


@router.get("/people/", response_class=HTMLResponse)
def people_list(
    request: Request,
    q: str = "",
    sort: str = Query(default="created_at"),
    dir: str = Query(default="desc"),
    company_priority: str = Query(default=""),
    value_rating: str = Query(default=""),
    linkedin: str = Query(default=""),
    deleted: bool = Query(default=False),
):
    people = get_people(
        q, sort, dir, request.session.get("user_id"), company_priority, value_rating,
        linkedin,
    )
    return templates.TemplateResponse("people.html", {
        "request": request,
        "people": people,
        "query": q,
        "sort": sort,
        "dir": dir,
        "company_priority": company_priority,
        "value_rating": value_rating,
        "linkedin": linkedin,
        "deleted": deleted,
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


def _import_page(request: Request, result=None, error=None, status_code: int = 200):
    return templates.TemplateResponse(
        "linkedin_import.html",
        {"request": request, "result": result, "error": error},
        status_code=status_code,
    )


@router.get("/people/import/linkedin", response_class=HTMLResponse)
def linkedin_import_form(request: Request):
    return _import_page(request)


@router.post("/people/import/linkedin", response_class=HTMLResponse)
def linkedin_import_upload(
    request: Request,
    connections: UploadFile = File(...),
    _admin: str = Depends(require_admin),
):
    """Import LinkedIn's Connections.csv data export as people. Rows are
    independent — one unreadable row is counted, never fatal."""
    data = connections.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        return _import_page(request, error="linkedin.import.errorEmpty", status_code=400)
    if len(data) > MAX_UPLOAD_BYTES:
        return _import_page(request, error="linkedin.import.errorTooLarge", status_code=413)
    parsed = parse_connections_csv(decode_export(data))
    if not parsed.header_found:
        return _import_page(request, error="linkedin.import.errorFormat", status_code=400)
    try:
        counts = import_connections(parsed.rows)
    except Exception:
        logger.exception("linkedin import failed")
        return _import_page(request, error="linkedin.import.errorFailed", status_code=500)
    counts["skipped"] = parsed.skipped
    counts["total"] = len(parsed.rows)
    log_audit(
        None, None, "person.linkedin_imported", "people",
        f"created:{counts['created']} updated:{counts['updated']} "
        f"skipped:{counts['skipped']} failed:{counts['failed']}",
    )
    return _import_page(request, result=counts)


@router.get("/people/linkedin/matches", response_class=HTMLResponse)
def linkedin_matches(
    request: Request,
    page: int = Query(default=1, ge=1),
    linked: int | None = Query(default=None),
    rejected: int | None = Query(default=None),
):
    """Review which organization each LinkedIn connection works at. Paged: with
    1,500 connections one page of rows is over a megabyte. Applying a page
    removes its decided rows, so the undecided ones simply move up."""
    load_failed = False
    try:
        suggestions = get_match_suggestions()
    except Exception:
        logger.exception("linkedin match suggestions failed")
        suggestions, load_failed = [], True
    total = len(suggestions)
    total_pages = max(1, -(-total // MATCH_PAGE_SIZE))
    page = min(page, total_pages)
    start = (page - 1) * MATCH_PAGE_SIZE
    return templates.TemplateResponse("linkedin_matches.html", {
        "request": request,
        "suggestions": suggestions[start:start + MATCH_PAGE_SIZE],
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "load_failed": load_failed,
        "applied": None if linked is None else {"linked": linked, "rejected": rejected or 0},
    })


def _parse_match_decisions(form) -> list[dict]:
    """The review form posts one `person_<id>` choice per row ('' = leave for
    later, 'none' = none of the offered organizations, else an organization id)
    plus `cands_<id>`, the ids that row offered. A link is honoured only to an
    organization that was actually offered for that person."""
    decisions = []
    for key in form.keys():
        if not key.startswith("person_") or not key[len("person_"):].isdigit():
            continue
        person_id = int(key[len("person_"):])
        choice = str(form.get(key) or "").strip()
        offered = [
            int(part) for part in str(form.get(f"cands_{person_id}") or "").split(",")
            if part.strip().isdigit()
        ]
        if choice == "none":
            decisions.append({"person_id": person_id, "contact_id": None, "rejected": offered})
        elif choice.isdigit() and int(choice) in offered:
            decisions.append({"person_id": person_id, "contact_id": int(choice), "rejected": []})
    return decisions


@router.post("/people/linkedin/matches")
async def linkedin_matches_apply(request: Request, _admin: str = Depends(require_admin)):
    decisions = _parse_match_decisions(await request.form())
    counts = apply_match_decisions(decisions) if decisions else {"linked": 0, "rejected": 0}
    log_audit(
        None, None, "person.linkedin_matches_applied", "people",
        f"linked:{counts['linked']} rejected:{counts['rejected']}",
    )
    return local_redirect(
        "/people/linkedin/matches", linked=str(counts["linked"]), rejected=str(counts["rejected"]),
    )


@router.get("/people/linkedin/cities", response_class=HTMLResponse)
def linkedin_cities(
    request: Request,
    page: int = Query(default=1, ge=1),
    saved: int | None = Query(default=None),
    dismissed: int | None = Query(default=None),
    failed: int | None = Query(default=None),
):
    """Organizations created from LinkedIn that still need a city, most
    connections first. The lookup could not settle these (chains, unknown or
    unlooked-up companies); a city typed here is saved as entered by hand."""
    load_failed = False
    try:
        queue = get_city_review_queue(page)
    except Exception:
        logger.exception("linkedin city queue failed")
        queue, load_failed = {"total": 0, "rows": []}, True
    total_pages = max(1, -(-queue["total"] // CITY_QUEUE_PAGE_SIZE))
    return templates.TemplateResponse("linkedin_cities.html", {
        "request": request,
        "rows": queue["rows"],
        "total": queue["total"],
        "page": min(page, total_pages),
        "total_pages": total_pages,
        "load_failed": load_failed,
        "applied": None if saved is None else {
            "saved": saved, "dismissed": dismissed or 0, "failed": failed or 0},
    })


def _parse_city_decisions(form) -> list[dict]:
    """One `city_<id>` text box, one `pick_<id>` choice ('City|CC' from the
    cities the lookup offered), `country_<id>`, and a `dismiss_<id>` checkbox per
    row. Typed text wins over the pick; empty rows are left alone."""
    ids = {
        int(key.split("_", 1)[1]) for key in form.keys()
        if key.split("_", 1)[0] in {"city", "pick", "country", "dismiss"}
        and key.split("_", 1)[-1].isdigit()
    }
    decisions = []
    for contact_id in sorted(ids):
        typed = str(form.get(f"city_{contact_id}") or "").strip()
        picked_city, _, picked_country = str(form.get(f"pick_{contact_id}") or "").partition("|")
        city = typed or picked_city.strip()
        country = str(form.get(f"country_{contact_id}") or "").strip()
        if not typed and not country:
            country = picked_country.strip()
        dismiss = bool(form.get(f"dismiss_{contact_id}")) and not city
        if city or dismiss:
            decisions.append({"contact_id": contact_id, "city": city,
                              "country": country, "dismiss": dismiss})
    return decisions


@router.post("/people/linkedin/cities")
async def linkedin_cities_apply(request: Request, _admin: str = Depends(require_admin)):
    decisions = _parse_city_decisions(await request.form())
    counts = apply_city_decisions(decisions) if decisions else {"saved": 0, "dismissed": 0, "failed": 0}
    log_audit(
        None, None, "contact.linkedin_cities_applied", "contacts",
        f"saved:{counts['saved']} dismissed:{counts['dismissed']} failed:{counts['failed']}",
    )
    return local_redirect(
        "/people/linkedin/cities", saved=str(counts["saved"]),
        dismissed=str(counts["dismissed"]), failed=str(counts["failed"]),
    )


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
        "people_retention_days": PEOPLE_RETENTION_DAYS,
    })


@router.get("/people/{person_id}/link", response_class=HTMLResponse)
def person_link_form(request: Request, person_id: int, q: str | None = Query(default=None)):
    """Find an organization to link this person to. The search starts from the
    company name the person has on LinkedIn, when there is one."""
    person = get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    term = q if q is not None else (person.get("company_raw") or "")
    return templates.TemplateResponse("person_link.html", {
        "request": request,
        "person": person,
        "q": term,
        "results": search_organizations(term),
    })


@router.post("/people/{person_id}/link")
def person_link(person_id: int, contact_id: int = Form(...), _admin: str = Depends(require_admin)):
    if not set_person_organization(person_id, contact_id):
        raise HTTPException(status_code=404, detail="Person or organization not found")
    log_audit(None, None, "person.linked", f"person:{person_id}", f"contact:{contact_id}")
    return local_redirect(f"/people/{person_id}", saved="1")


@router.post("/people/{person_id}/unlink")
def person_unlink(person_id: int, _admin: str = Depends(require_admin)):
    if not set_person_organization(person_id, None):
        raise HTTPException(status_code=404, detail="Person not found")
    log_audit(None, None, "person.unlinked", f"person:{person_id}", "unlinked")
    return local_redirect(f"/people/{person_id}", saved="1")


@router.post("/people/{person_id}/delete")
def person_delete(person_id: int, _admin: str = Depends(require_admin)):
    """Permanently delete one person (no undo). A person with a LinkedIn URL leaves
    only its hash behind, so the next LinkedIn import does not bring them back."""
    if not erase_person(person_id):
        raise HTTPException(status_code=404, detail="Person not found")
    return local_redirect("/people/", deleted="1")


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
    linkedin_url: str = Form(""),
    is_linkedin_contact: bool = Form(False),
    retention_hold: bool = Form(False),
    _admin: str = Depends(require_admin),
):
    """Save the edited person. Name is the one field the row cannot lose."""
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    try:
        updated = update_person(person_id, {
            "name": name, "title": title, "email": email, "phone": phone,
            "website": website, "city": city, "country": country,
            "relationship": relationship, "met_at": met_at, "notes": notes,
            "linkedin_url": linkedin_url, "is_linkedin_contact": is_linkedin_contact,
            "retention_hold": retention_hold,
        })
    except ValueError:
        raise HTTPException(status_code=400, detail="LinkedIn URL must be a linkedin.com link")
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
