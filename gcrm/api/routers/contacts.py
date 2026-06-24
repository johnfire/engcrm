from fastapi import APIRouter, Depends, Request, Query, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional
from gcrm.db.connection import db
from gcrm.api.auth import require_login, require_admin

router = APIRouter(prefix="/contacts", tags=["contacts"], dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))
templates.env.filters["urlenc"] = quote_plus

VALID_STATUSES = (
    "candidate", "cold", "contacted", "meeting", "proposal",
    "accepted", "rejected", "dormant", "on_hold", "dropped", "do_not_contact",
    "networking_visit", "bad_email", "cannot_find_more_data",
)

PAGE_SIZE = 100

SORT_COLUMNS = {
    "id":           "c.id",
    "name":         "lower(c.name)",
    "city":         "lower(c.city)",
    "type":         "lower(c.type)",
    "status":       "c.status",
    "fit":          "c.fit_score",
    "last_contact": "MAX(i.interaction_date)",
}


@router.get("/", response_class=HTMLResponse)
def contact_list(
    request: Request,
    status: str = Query(default=""),
    type: str = Query(default=""),
    q: str = Query(default=""),
    has_contact: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    sort: str = Query(default="id"),
    dir: str = Query(default="asc"),
):
    offset = (page - 1) * PAGE_SIZE
    sort_col = SORT_COLUMNS.get(sort, "c.id")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    with db() as conn:
        cur = conn.cursor()

        conditions = ["c.deleted_at IS NULL"]
        params = []
        if status:
            conditions.append("c.status = %s")
            params.append(status)
        if type:
            conditions.append("lower(c.type) = lower(%s)")
            params.append(type)
        if q:
            conditions.append("(lower(c.name) LIKE %s OR lower(c.city) LIKE %s)")
            params += [f"%{q.lower()}%", f"%{q.lower()}%"]
        if has_contact == "1":
            conditions.append("c.id IN (SELECT DISTINCT contact_id FROM interactions)")
        elif has_contact == "0":
            conditions.append("c.id NOT IN (SELECT DISTINCT contact_id FROM interactions)")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(
            f"SELECT COUNT(DISTINCT c.id) AS cnt FROM contacts c {where}",
            params,
        )
        total = cur.fetchone()["cnt"]

        cur.execute(
            f"""
            SELECT
                c.id, c.name, c.city, c.country, c.type, c.status,
                c.email, c.website, c.fit_score, c.notes, c.flagged, c.starred,
                MAX(i.interaction_date) AS last_contact
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            {where}
            GROUP BY c.id
            ORDER BY {sort_col} {sort_dir} NULLS LAST
            LIMIT {PAGE_SIZE} OFFSET {offset}
            """,
            params,
        )
        contacts = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT status FROM contacts WHERE status IS NOT NULL ORDER BY status")
        statuses = [r["status"] for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT type FROM contacts WHERE type IS NOT NULL AND type != '' ORDER BY type")
        types = [r["type"] for r in cur.fetchall()]

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse("contacts.html", {
        "request": request,
        "contacts": contacts,
        "statuses": statuses,
        "types": types,
        "active_status": status,
        "active_type": type,
        "query": q,
        "has_contact": has_contact,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "sort": sort,
        "dir": dir,
    })


@router.get("/print", response_class=HTMLResponse)
def contact_print(
    request: Request,
    status: str = Query(default=""),
    type: str = Query(default=""),
    q: str = Query(default=""),
    sort: str = Query(default="id"),
    dir: str = Query(default="asc"),
):
    sort_col = SORT_COLUMNS.get(sort, "c.id")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    with db() as conn:
        cur = conn.cursor()

        conditions = ["c.deleted_at IS NULL"]
        params = []
        if status:
            conditions.append("c.status = %s")
            params.append(status)
        if type:
            conditions.append("lower(c.type) = lower(%s)")
            params.append(type)
        if q:
            conditions.append("(lower(c.name) LIKE %s OR lower(c.city) LIKE %s)")
            params += [f"%{q.lower()}%", f"%{q.lower()}%"]

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(
            f"""
            SELECT
                c.id, c.name, c.city, c.country, c.type, c.status,
                c.email, c.website, c.fit_score, c.notes,
                MAX(i.interaction_date) AS last_contact
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            {where}
            GROUP BY c.id
            ORDER BY {sort_col} {sort_dir} NULLS LAST
            """,
            params,
        )
        contacts = [dict(r) for r in cur.fetchall()]

    from datetime import date
    active_filters = []
    if status:
        active_filters.append(f"status: {status}")
    if type:
        active_filters.append(f"type: {type}")
    if q:
        active_filters.append(f"search: {q}")

    return templates.TemplateResponse("contacts_print.html", {
        "request": request,
        "contacts": contacts,
        "active_filters": active_filters,
        "total": len(contacts),
        "now": date.today().isoformat(),
    })


@router.get("/{contact_id}/brief", response_class=HTMLResponse)
def contact_brief(contact_id: int, request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contacts WHERE id = %s AND deleted_at IS NULL", (contact_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        contact = dict(row)
        cur.execute(
            "SELECT interaction_date, method, direction, summary, outcome, next_action, next_action_date FROM interactions WHERE contact_id = %s ORDER BY interaction_date DESC LIMIT 5",
            (contact_id,),
        )
        interactions = [dict(r) for r in cur.fetchall()]
    return templates.TemplateResponse("contact_brief.html", {
        "request": request,
        "contact": contact,
        "interactions": interactions,
    })


@router.get("/{contact_id}", response_class=HTMLResponse)
def contact_detail(contact_id: int, request: Request, saved: bool = Query(default=False)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contacts WHERE id = %s AND deleted_at IS NULL", (contact_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        contact = dict(row)
        cur.execute(
            "SELECT interaction_date, method, direction, summary, outcome, next_action, next_action_date FROM interactions WHERE contact_id = %s ORDER BY interaction_date DESC LIMIT 20",
            (contact_id,),
        )
        interactions = [dict(r) for r in cur.fetchall()]
    return templates.TemplateResponse("contact_detail.html", {
        "request": request,
        "contact": contact,
        "interactions": interactions,
        "valid_statuses": VALID_STATUSES,
        "saved": saved,
    })


@router.post("/{contact_id}/edit")
def contact_edit(
    contact_id: int,
    request: Request,
    name: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    type: str = Form(""),
    status: str = Form(""),
    fit_score: Optional[str] = Form(None),
    email: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    preferred_contact_method: str = Form(""),
    decision_maker: str = Form(""),
    last_visited_at: Optional[str] = Form(None),
    best_visit_time: str = Form(""),
    visit_duration: str = Form(""),
    first_impression: str = Form(""),
    last_impression: str = Form(""),
    materials_left: str = Form(""),
    followup_promised: str = Form(""),
    access_notes: str = Form(""),
    space_notes: str = Form(""),
    price_sensitivity: str = Form(""),
    notes: str = Form(""),
    _admin: str = Depends(require_admin),
):
    def empty_none(v):
        return v if v and v.strip() else None

    score = None
    if fit_score and fit_score.strip():
        try:
            score = int(fit_score)
        except ValueError:
            pass

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE contacts SET
                name = %s, city = %s, country = %s, type = %s, status = %s,
                fit_score = %s, email = %s, phone = %s, website = %s,
                preferred_contact_method = %s, decision_maker = %s,
                last_visited_at = %s, best_visit_time = %s, visit_duration = %s,
                first_impression = %s, last_impression = %s,
                materials_left = %s, followup_promised = %s,
                access_notes = %s, space_notes = %s, price_sensitivity = %s,
                notes = %s, updated_at = NOW()
            WHERE id = %s AND deleted_at IS NULL
            """,
            (
                empty_none(name), empty_none(city), empty_none(country), empty_none(type),
                empty_none(status), score,
                empty_none(email), empty_none(phone), empty_none(website),
                empty_none(preferred_contact_method), empty_none(decision_maker),
                empty_none(last_visited_at), empty_none(best_visit_time), empty_none(visit_duration),
                empty_none(first_impression), empty_none(last_impression),
                empty_none(materials_left), empty_none(followup_promised),
                empty_none(access_notes), empty_none(space_notes), empty_none(price_sensitivity),
                empty_none(notes), contact_id,
            ),
        )
    return RedirectResponse(url=f"/contacts/{contact_id}?saved=1", status_code=303)


@router.post("/{contact_id}/delete")
def delete_contact(contact_id: int, request: Request, _admin: str = Depends(require_admin)):
    # Soft delete: set deleted_at (the model used everywhere else) so the row
    # leaves listings but isn't irreversibly destroyed.
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET deleted_at = NOW(), updated_at = NOW() WHERE id = %s AND deleted_at IS NULL",
            (contact_id,),
        )
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)


@router.post("/{contact_id}/unflag")
def unflag_contact(contact_id: int, request: Request, _admin: str = Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET flagged = FALSE WHERE id = %s", (contact_id,))
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)


@router.post("/{contact_id}/star", response_class=HTMLResponse)
def toggle_star(contact_id: int, request: Request, _admin: str = Depends(require_admin)):
    """Toggle a contact's favourite star and return the refreshed button (HTMX swap)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET starred = NOT starred WHERE id = %s RETURNING starred",
            (contact_id,),
        )
        row = cur.fetchone()
    starred = bool(row["starred"]) if row else False
    return templates.TemplateResponse(
        "partials/star_button.html",
        {"request": request, "c": {"id": contact_id, "starred": starred}},
    )
