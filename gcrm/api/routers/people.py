import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gcrm.activity_types import PERSON_METHODS, parse_minutes
from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.routers.api_people import PERSON_LIMITS, PersonFields
from gcrm.api.routers.api_record_edit import clean_fields
from gcrm.api.templates import templates
from gcrm.config import MAIL_SENDER_OPTIONS, MAX_UPLOAD_BYTES, PEOPLE_RETENTION_DAYS
from gcrm.db.connection import db
from gcrm.linkedin import decode_export, parse_connections_csv
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.company_places import ESTIMATED_USD_PER_1000
from gcrm.tools.curiosity_email import draft_curiosity_email
from gcrm.tools.db_approvals import queue_person_draft
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_company_web import JOB_MAX, count_web_work, is_job_running, start_web_job
from gcrm.tools.db_linkedin import (
    CITY_QUEUE_PAGE_SIZE,
    JOB_CHANGE_PAGE_SIZE,
    WEB_LOOKUP_MAX,
    apply_city_decisions,
    apply_company_change_decisions,
    apply_match_decisions,
    count_city_work,
    get_city_review_queue,
    get_company_changes,
    get_company_promotion_plan,
    get_match_suggestions,
    import_connections,
    promote_linkedin_companies,
    run_city_lookup,
)
from gcrm.tools.db_people import (
    find_existing_person,
    get_people,
    get_person,
    get_person_cities,
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
from gcrm.tools.people_next_step import set_person_next_step
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


class PersonStageBody(BaseModel):
    stage: str | None = None  # null or blank clears the stage


def remember_people_stage(request: Request, stage: str | None) -> str:
    selected_stage = stage if stage is not None else request.session.get("people_stage", "")
    if selected_stage not in (*PIPELINE_STAGES, "none", ""):
        selected_stage = ""
    request.session["people_stage"] = selected_stage
    return selected_stage


@router.get("/people/", response_class=HTMLResponse)
def people_list(
    request: Request,
    q: str = "",
    sort: str = Query(default="created_at"),
    dir: str = Query(default="desc"),
    company_priority: str = Query(default=""),
    value_rating: str = Query(default=""),
    linkedin: str = Query(default=""),
    stage: str | None = Query(default=None),
    city: str = Query(default=""),
    deleted: bool = Query(default=False),
):
    stage = remember_people_stage(request, stage)
    people = get_people(
        q, sort, dir, request.session.get("user_id"), company_priority, value_rating,
        linkedin, stage=stage, city=city,
    )
    return templates.TemplateResponse("people.html", {
        "request": request,
        "people": people,
        "today": date.today().isoformat(),
        "query": q,
        "sort": sort,
        "dir": dir,
        "company_priority": company_priority,
        "value_rating": value_rating,
        "linkedin": linkedin,
        "stage": stage,
        "city": city,
        "cities": get_person_cities(),
        "stages": PIPELINE_STAGES,
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


def _new_person_page(
    request: Request, values: dict | None = None, error: str | None = None,
    existing: dict | None = None, status_code: int = 200,
):
    """The New person form. After a refused save it comes back with everything
    typed still in place, plus the reason (`error`) or the person it matched
    (`existing`)."""
    return templates.TemplateResponse(
        "person_new.html",
        {"request": request, "stages": PIPELINE_STAGES, "values": values or {},
         "error": error, "existing": existing, "limits": PERSON_LIMITS},
        status_code=status_code,
    )


@router.get("/people/new", response_class=HTMLResponse)
def person_new(request: Request):
    return _new_person_page(request)


@router.post("/people/new")
def person_create(
    request: Request,
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
    pipeline_stage: str = Form(""),
    allow_duplicate: bool = Form(False),
    _admin: str = Depends(require_admin),
):
    """Save a person typed in by hand. Same rules as the phone (POST /api/people):
    lengths and email checked, country upper-cased and DE when blank. Nothing typed
    is ever dropped: a refused save, or a match on someone already stored, brings
    the form back filled in rather than discarding it."""
    typed = {
        "name": name, "title": title, "email": email, "phone": phone, "website": website,
        "city": city, "country": country, "relationship": relationship, "met_at": met_at,
        "notes": notes,
    }
    values = {**typed, "pipeline_stage": pipeline_stage}
    try:
        fields = clean_fields(PersonFields(**typed), PERSON_LIMITS, require_name=True)
    except HTTPException as refused:
        return _new_person_page(request, values, error=refused.detail, status_code=400)
    if pipeline_stage and pipeline_stage not in PIPELINE_STAGES:
        return _new_person_page(request, values, error="Unknown pipeline stage", status_code=400)
    text = {column: value or "" for column, value in fields.items()}

    if not allow_duplicate:
        with db() as conn:
            existing_id = find_existing_person(conn.cursor(), text["name"], text["email"], None)
        if existing_id:
            existing = get_person(existing_id) or {"id": existing_id, "name": text["name"]}
            return _new_person_page(request, values, existing=existing, status_code=409)

    person_id = save_person(
        name=text["name"], title=text["title"], email=text["email"], phone=text["phone"],
        website=text["website"], city=text["city"], country=text["country"] or "DE",
        relationship=text["relationship"], notes=text["notes"], met_at=text["met_at"],
        source="manual", pipeline_stage=pipeline_stage, allow_duplicate=allow_duplicate,
    )
    log_audit(None, None, "person.created", f"person:{person_id}",
              "created:confirmed-not-duplicate" if allow_duplicate else "created")
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
    looked_up: int | None = Query(default=None),
    resolved: int | None = Query(default=None),
    ambiguous: int | None = Query(default=None),
    not_found: int | None = Query(default=None),
    errors: int | None = Query(default=None),
    stopped: str = Query(default=""),
    started: int | None = Query(default=None),
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
        "lookup": _city_lookup_panel(),
        "web": _web_panel(),
        "job_started": started,
        "lookup_result": None if looked_up is None else {
            "looked_up": looked_up, "resolved": resolved or 0, "ambiguous": ambiguous or 0,
            "not_found": not_found or 0, "errors": errors or 0, "stopped": stopped,
            "estimate": round(looked_up * ESTIMATED_USD_PER_1000 / 1000, 2)},
    })


def _city_lookup_panel() -> dict:
    """What the 'Look up cities' button would do right now, for the page."""
    from gcrm.config import GOOGLE_MAPS_API_KEY
    try:
        work = count_city_work()
    except Exception:
        logger.exception("city work count failed")
        work = {"to_lookup": 0, "cached_ready": 0, "failed": True}
    return {"key_set": bool(GOOGLE_MAPS_API_KEY), "max": WEB_LOOKUP_MAX,
            "per_1000": ESTIMATED_USD_PER_1000, **work}


def _web_panel() -> dict:
    """What the 'Find websites and addresses' button would do, and whether a job is
    running right now (the page refreshes itself while it is)."""
    try:
        work, running = count_web_work(), is_job_running()
    except Exception:
        logger.exception("web lookup panel failed")
        work, running = {"to_lookup": 0, "retry": 0, "review": 0, "cached_ready": 0, "failed": True}, False
    return {"max": JOB_MAX, "running": running, **work}


@router.post("/people/linkedin/cities/web")
def linkedin_cities_web(limit: int = Form(50), _admin: str = Depends(require_admin)):
    """Start the website + address search in the background (it takes ~10 s per
    company). Nothing is billed: it uses web search and the companies' own pages."""
    started = start_web_job(limit)
    log_audit(None, None, "contact.linkedin_web_lookup", "contacts", f"limit:{limit} started:{started}")
    return local_redirect("/people/linkedin/cities", started="1" if started else "0")


@router.post("/people/linkedin/cities/lookup")
def linkedin_cities_lookup(limit: int = Form(5), _admin: str = Depends(require_admin)):
    """Look up the city of up to `limit` (1..WEB_LOOKUP_MAX) companies in Google
    Places. Each lookup is billed, so the page states the count and estimate
    first, the limit is capped, and only one run can go at a time."""
    try:
        counts = run_city_lookup(limit)
    except Exception:
        logger.exception("city lookup run failed")
        counts = {"looked_up": 0, "resolved": 0, "ambiguous": 0, "not_found": 0,
                  "errors": 1, "stopped": "the lookup could not run"}
    log_audit(None, None, "contact.linkedin_cities_lookup", "contacts",
              f"looked_up:{counts['looked_up']} resolved:{counts['resolved']}")
    return local_redirect(
        "/people/linkedin/cities", looked_up=str(counts["looked_up"]), resolved=str(counts["resolved"]),
        ambiguous=str(counts["ambiguous"]), not_found=str(counts["not_found"]),
        errors=str(counts["errors"]), stopped=counts["stopped"], saved="0",
    )


def _parse_city_decisions(form) -> list[dict]:
    """One `city_<id>` text box, one `pick_<id>` choice ('City|CC' from the
    cities the lookup offered), `country_<id>`, and a `dismiss_<id>` checkbox per
    row. Typed text wins over the pick; empty rows are left alone."""
    ids = {
        int(key.split("_", 1)[1]) for key in form.keys()
        if key.split("_", 1)[0] in {"city", "pick", "country", "dismiss", "accept"}
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
        accept = bool(form.get(f"accept_{contact_id}")) and not city
        dismiss = bool(form.get(f"dismiss_{contact_id}")) and not city and not accept
        if city or dismiss or accept:
            decisions.append({"contact_id": contact_id, "city": city, "country": country,
                              "dismiss": dismiss, "accept": accept})
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


@router.get("/people/linkedin/job-changes", response_class=HTMLResponse)
def linkedin_job_changes(
    request: Request,
    page: int = Query(default=1, ge=1),
    moved: int | None = Query(default=None),
    kept: int | None = Query(default=None),
    failed: int | None = Query(default=None),
):
    """Connections whose newer export shows a different employer. Nothing is
    applied automatically: a person you linked to an organization stays there
    until you say they moved."""
    load_failed = False
    try:
        result = get_company_changes(page)
    except Exception:
        logger.exception("linkedin job changes failed")
        result, load_failed = {"total": 0, "rows": []}, True
    total_pages = max(1, -(-result["total"] // JOB_CHANGE_PAGE_SIZE))
    return templates.TemplateResponse("linkedin_job_changes.html", {
        "request": request,
        "rows": result["rows"],
        "total": result["total"],
        "page": min(page, total_pages),
        "total_pages": total_pages,
        "load_failed": load_failed,
        "applied": None if moved is None else {"moved": moved, "kept": kept or 0, "failed": failed or 0},
    })


def _parse_job_change_decisions(form) -> list[dict]:
    """`change_<id>` is '' (decide later), 'move' or 'keep'; `seen_<id>` is the
    pending company the row showed."""
    decisions = []
    for key in form.keys():
        if not key.startswith("change_") or not key[len("change_"):].isdigit():
            continue
        person_id = int(key[len("change_"):])
        action = str(form.get(key) or "").strip()
        seen = str(form.get(f"seen_{person_id}") or "")
        if action in {"move", "keep"} and seen:
            decisions.append({"person_id": person_id, "action": action, "seen": seen})
    return decisions


@router.post("/people/linkedin/job-changes")
async def linkedin_job_changes_apply(request: Request, _admin: str = Depends(require_admin)):
    decisions = _parse_job_change_decisions(await request.form())
    counts = (apply_company_change_decisions(decisions) if decisions
              else {"moved": 0, "kept": 0, "failed": 0})
    log_audit(
        None, None, "person.linkedin_job_changes_applied", "people",
        f"moved:{counts['moved']} kept:{counts['kept']} failed:{counts['failed']}",
    )
    return local_redirect(
        "/people/linkedin/job-changes", moved=str(counts["moved"]),
        kept=str(counts["kept"]), failed=str(counts["failed"]),
    )


COMPANY_PREVIEW_SAMPLE = 25


@router.get("/people/linkedin/companies", response_class=HTMLResponse)
def linkedin_companies(
    request: Request,
    created: int | None = Query(default=None),
    linked: int | None = Query(default=None),
    people: int | None = Query(default=None),
    failed: int | None = Query(default=None),
    ambiguous: int | None = Query(default=None),
):
    """Preview, then create, the organizations for the companies your LinkedIn
    connections work at. Reading the preview writes nothing."""
    load_failed, plan = False, None
    try:
        plan = get_company_promotion_plan()
    except Exception:
        logger.exception("linkedin company plan failed")
        load_failed = True

    def largest(groups):
        return sorted(groups, key=lambda g: (-len(g["people_ids"]), g["name"].lower()))[:COMPANY_PREVIEW_SAMPLE]

    return templates.TemplateResponse("linkedin_companies.html", {
        "request": request,
        "plan": plan,
        "load_failed": load_failed,
        "people_in": (lambda groups: sum(len(g["people_ids"]) for g in groups)),
        "create_sample": largest(plan.create) if plan else [],
        "link_sample": largest(plan.link) if plan else [],
        "ambiguous_sample": largest(plan.ambiguous) if plan else [],
        "applied": None if created is None else {
            "created": created, "linked": linked or 0, "people": people or 0,
            "failed": failed or 0, "ambiguous": ambiguous or 0},
    })


@router.post("/people/linkedin/companies")
def linkedin_companies_apply(_admin: str = Depends(require_admin)):
    """Create the organizations. The plan is recomputed here, not taken from the
    form, so a stale preview can never apply old decisions."""
    try:
        counts = promote_linkedin_companies()
    except Exception:
        logger.exception("linkedin company promotion failed")
        counts = {"created": 0, "linked": 0, "people_linked": 0, "failed": 1, "ambiguous_skipped": 0}
    return local_redirect(
        "/people/linkedin/companies", created=str(counts["created"]), linked=str(counts["linked"]),
        people=str(counts["people_linked"]), failed=str(counts["failed"]),
        ambiguous=str(counts["ambiguous_skipped"]),
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
        "stages": PIPELINE_STAGES,
        "today": date.today().isoformat(),
    })


@router.post("/people/{person_id}/next-step")
def person_set_next_step(
    person_id: int,
    next_step: str = Form(""),
    next_step_date: str = Form(""),
    done: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Set what happens next with this person, or mark it done (clears it). Each
    change is also written to the note log by set_person_next_step."""
    try:
        due = date.fromisoformat(next_step_date) if next_step_date.strip() and not done else None
        result = set_person_next_step(person_id, "" if done else next_step, due)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if result is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return local_redirect(f"/people/{person_id}", saved="1")


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


@router.post("/people/{person_id}/stage")
def person_set_stage(
    person_id: int,
    stage: str = Form(""),
    next: str = Form("/people/"),
    _admin: str = Depends(require_admin),
):
    """Change a person's stage from the list (blank clears it) and come back to
    the same filtered list."""
    if stage and stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    if not update_person(person_id, {"pipeline_stage": stage}):
        raise HTTPException(status_code=404, detail="Person not found")
    log_audit(None, None, "person.stage_changed", f"person:{person_id}", stage or "cleared")
    return local_redirect(next, fallback="/people/")


@router.put("/people/{person_id}/stage")
def person_put_stage(
    person_id: int,
    body: PersonStageBody,
    _admin: str = Depends(require_admin),
):
    """Change a person's stage from their detail page the moment it is picked, without
    leaving the page — so edits not yet saved in the other fields are kept."""
    stage = (body.stage or "").strip()
    if stage and stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    if not update_person(person_id, {"pipeline_stage": stage}):
        raise HTTPException(status_code=404, detail="Person not found")
    log_audit(None, None, "person.stage_changed", f"person:{person_id}", stage or "cleared")
    return {"pipeline_stage": stage or None}


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
    pipeline_stage: str | None = Form(None),
    _admin: str = Depends(require_admin),
):
    """Save the edited person. Name is the one field the row cannot lose."""
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if pipeline_stage and pipeline_stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    try:
        updated = update_person(person_id, {
            "name": name, "title": title, "email": email, "phone": phone,
            "website": website, "city": city, "country": country,
            "relationship": relationship, "met_at": met_at, "notes": notes,
            "linkedin_url": linkedin_url, "is_linkedin_contact": is_linkedin_contact,
            "retention_hold": retention_hold,
            # absent from an old cached form -> leave the stored stage alone
            **({} if pipeline_stage is None else {"pipeline_stage": pipeline_stage}),
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
    duration_minutes: str = Form(""),
    _admin: str = Depends(require_admin),
):
    if get_person(person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    if not note.strip():
        raise HTTPException(status_code=400, detail="Note is required")
    if method.strip() and method.strip() not in PERSON_METHODS:
        raise HTTPException(status_code=400, detail="Unknown method")
    try:
        minutes = parse_minutes(duration_minutes)
    except ValueError:
        raise HTTPException(status_code=400, detail="Minutes must be a whole number from 0 to 1440")
    log_person_note(person_id, method.strip() or None, note.strip(), duration_minutes=minutes)
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
