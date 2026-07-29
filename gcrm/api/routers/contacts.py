from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from gcrm.api.auth import require_admin, require_login
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.supervisor.contact_opportunity_analysis import analyse_contact_opportunity
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_personal_priorities import set_personal_priority
from gcrm.tools.privacy_retention import erase_contact

router = APIRouter(prefix="/contacts", tags=["contacts"], dependencies=[Depends(require_login)])

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
    "personal_priority": "cup.priority",
    "starred":      "c.starred",
    "last_contact": "MAX(i.interaction_date)",
    "created_at":   "c.created_at",
}


class PersonalPriorityBody(BaseModel):
    priority: int | None = None


def _priority_join(user_id: int | None) -> tuple[str, list]:
    if user_id is None:
        return "LEFT JOIN contact_user_priorities cup ON FALSE", []
    return (
        "LEFT JOIN contact_user_priorities cup "
        "ON cup.contact_id = c.id AND cup.user_id = %s",
        [user_id],
    )


def _build_contact_filters(status, type, q, has_contact, personal_priority="", workspace_id=None):
    """Build the WHERE clause + bound params for the contact list from the query
    filters. The name/city search is a parenthesized OR so it can't leak past an
    AND — don't regress that."""
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
    if personal_priority in {"1", "2", "3", "4", "5"}:
        conditions.append("cup.priority = %s")
        params.append(int(personal_priority))
    elif personal_priority == "unrated":
        conditions.append("cup.priority IS NULL")
    if workspace_id is not None:
        conditions.append("c.workspace_id = %s")
        params.append(workspace_id)

    where = "WHERE " + " AND ".join(conditions)
    return where, params


def _fetch_contacts_page(where, params, sort_col, sort_dir, offset, user_id=None, workspace_id=None):
    """Run the count + page queries for the given filters and gather the distinct
    status/type option lists. Returns (contacts, statuses, types, total)."""
    with db() as conn:
        cur = conn.cursor()
        priority_join, priority_params = _priority_join(user_id)
        query_params = priority_params + params

        cur.execute(
            f"SELECT COUNT(DISTINCT c.id) AS cnt FROM contacts c {priority_join} {where}",
            query_params,
        )
        total = cur.fetchone()["cnt"]

        cur.execute(
            f"""
            SELECT
                c.id, c.name, c.city, c.country, c.type, c.status,
                c.email, c.website, c.fit_score, c.notes, c.flagged, c.starred,
                c.created_at, cup.priority AS personal_priority,
                MAX(i.interaction_date) AS last_contact
            FROM contacts c
            {priority_join}
            LEFT JOIN interactions i ON i.contact_id = c.id
            {where}
            GROUP BY c.id, cup.priority
            ORDER BY {sort_col} {sort_dir} NULLS LAST, c.id ASC
            LIMIT {PAGE_SIZE} OFFSET {offset}
            """,
            query_params,
        )
        contacts = [dict(row) for row in cur.fetchall()]

        workspace_filter = " AND workspace_id = %s" if workspace_id is not None else ""
        workspace_params = [workspace_id] if workspace_id is not None else []
        cur.execute(
            f"SELECT DISTINCT status FROM contacts "
            f"WHERE status IS NOT NULL{workspace_filter} ORDER BY status",
            workspace_params,
        )
        statuses = [row["status"] for row in cur.fetchall()]

        cur.execute(
            f"SELECT DISTINCT type FROM contacts "
            f"WHERE type IS NOT NULL AND type != ''{workspace_filter} ORDER BY type",
            workspace_params,
        )
        types = [row["type"] for row in cur.fetchall()]

    return contacts, statuses, types, total


@router.get("/", response_class=HTMLResponse)
def contact_list(
    request: Request,
    status: str = Query(default=""),
    type: str = Query(default=""),
    q: str = Query(default=""),
    has_contact: str = Query(default=""),
    personal_priority: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    sort: str = Query(default="created_at"),
    dir: str = Query(default="desc"),
):
    offset = (page - 1) * PAGE_SIZE
    sort_col = SORT_COLUMNS.get(sort, "c.created_at")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    user_id = request.session.get("user_id")
    workspace_id = request.session.get("workspace_id")
    where, params = _build_contact_filters(
        status, type, q, has_contact, personal_priority, workspace_id,
    )
    contacts, statuses, types, total = _fetch_contacts_page(
        where, params, sort_col, sort_dir, offset, user_id, workspace_id,
    )

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
        "personal_priority": personal_priority,
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
    personal_priority: str = Query(default=""),
    sort: str = Query(default="created_at"),
    dir: str = Query(default="desc"),
):
    sort_col = SORT_COLUMNS.get(sort, "c.created_at")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    # Same filters as the list view (no has_contact toggle on the print page).
    user_id = request.session.get("user_id")
    workspace_id = request.session.get("workspace_id")
    priority_join, priority_params = _priority_join(user_id)
    where, params = _build_contact_filters(
        status, type, q, "", personal_priority, workspace_id,
    )

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                c.id, c.name, c.city, c.country, c.type, c.status,
                c.email, c.website, c.fit_score, c.notes,
                cup.priority AS personal_priority,
                MAX(i.interaction_date) AS last_contact
            FROM contacts c
            {priority_join}
            LEFT JOIN interactions i ON i.contact_id = c.id
            {where}
            GROUP BY c.id, cup.priority
            ORDER BY {sort_col} {sort_dir} NULLS LAST, c.id ASC
            """,
            priority_params + params,
        )
        contacts = [dict(row) for row in cur.fetchall()]

    from datetime import date
    active_filters = []
    if status:
        active_filters.append(f"status: {status}")
    if type:
        active_filters.append(f"type: {type}")
    if q:
        active_filters.append(f"search: {q}")
    if personal_priority:
        active_filters.append(f"personal priority: {personal_priority}")

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
        interactions = [dict(row) for row in cur.fetchall()]
    return templates.TemplateResponse("contact_brief.html", {
        "request": request,
        "contact": contact,
        "interactions": interactions,
    })


@router.get("/{contact_id}", response_class=HTMLResponse)
def contact_detail(contact_id: int, request: Request, saved: bool = Query(default=False)):
    with db() as conn:
        cur = conn.cursor()
        user_id = request.session.get("user_id")
        workspace_id = request.session.get("workspace_id")
        priority_join, priority_params = _priority_join(user_id)
        workspace_filter = "AND c.workspace_id = %s" if workspace_id is not None else ""
        cur.execute(
            f"""
            SELECT c.*, cup.priority AS personal_priority
            FROM contacts c
            {priority_join}
            WHERE c.id = %s
              AND c.deleted_at IS NULL
              {workspace_filter}
            """,
            priority_params + [contact_id] + ([workspace_id] if workspace_id is not None else []),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        contact = dict(row)
        cur.execute(
            "SELECT interaction_date, method, direction, summary, outcome, next_action, next_action_date FROM interactions WHERE contact_id = %s ORDER BY interaction_date DESC LIMIT 20",
            (contact_id,),
        )
        interactions = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT fit_reasoning, suggested_approach, priority_score, opportunity_score,
                   confidence_score, evidence, recommended_services, discovery_questions,
                   analysis_date
            FROM ai_analysis
            WHERE contact_id = %s AND deleted_at IS NULL AND analysis_kind = 'opportunity'
            ORDER BY analysis_date DESC, id DESC
            LIMIT 1
            """,
            (contact_id,),
        )
        opportunity_analysis = cur.fetchone()
    return templates.TemplateResponse("contact_detail.html", {
        "request": request,
        "contact": contact,
        "interactions": interactions,
        "opportunity_analysis": dict(opportunity_analysis) if opportunity_analysis else None,
        "valid_statuses": VALID_STATUSES,
        "saved": saved,
        "opportunity_flash": request.session.pop("opportunity_flash", None),
    })


@router.put("/{contact_id}/personal-priority")
def update_personal_priority(
    contact_id: int,
    body: PersonalPriorityBody,
    request: Request,
):
    """Set or clear the signed-in user's private priority for one contact."""
    user_id = request.session.get("user_id")
    workspace_id = request.session.get("workspace_id")
    if user_id is None or workspace_id is None:
        raise HTTPException(status_code=403, detail="Personal account required")
    if body.priority is not None and body.priority not in range(1, 6):
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5")

    contact_found, stored_priority = set_personal_priority(
        user_id,
        workspace_id,
        contact_id,
        body.priority,
    )
    if not contact_found:
        raise HTTPException(status_code=404, detail="Contact not found")

    outcome = "cleared" if stored_priority is None else f"set:{stored_priority}"
    log_audit(
        None,
        None,
        "contact.personal_priority_changed",
        f"contact:{contact_id}",
        outcome,
    )
    return {"personal_priority": stored_priority}


@router.post("/{contact_id}/opportunity-analysis")
def analyse_selected_contact(
    contact_id: int,
    request: Request,
    _admin: str = Depends(require_admin),
):
    """Run a fresh analysis for exactly one contact; it never sends outreach."""
    log_audit(None, None, "contact.opportunity_analysis_requested", f"contact:{contact_id}", "started")
    try:
        result = analyse_contact_opportunity(contact_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Contact not found")
    except Exception as error:
        log_audit(None, None, "contact.opportunity_analysis_requested", f"contact:{contact_id}", "failed")
        request.session["opportunity_flash"] = {"error": str(error)}
        return RedirectResponse(url=f"/contacts/{contact_id}", status_code=303)
    log_audit(None, None, "contact.opportunity_analysis_requested", f"contact:{contact_id}", "completed")
    request.session["opportunity_flash"] = {"summary": result.get("summary", "Analysis complete")}
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=303)


def _persist_contact_edit(contact_id, text_fields, fit_score):
    """Normalize blank strings to NULL, parse the numeric fit_score, and write the
    contact row. text_fields maps column name -> submitted string."""
    def empty_none(value):
        return value if value and value.strip() else None

    score = None
    if fit_score and fit_score.strip():
        try:
            score = int(fit_score)
        except ValueError:
            pass

    updates = {column: empty_none(value) for column, value in text_fields.items()}
    updates["fit_score"] = score

    assignments = ", ".join(f"{column} = %s" for column in updates)
    values = list(updates.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {assignments}, updated_at = NOW() "
            f"WHERE id = %s AND deleted_at IS NULL",
            values,
        )


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
    text_fields = {
        "name": name, "city": city, "country": country, "type": type, "status": status,
        "email": email, "phone": phone, "website": website,
        "preferred_contact_method": preferred_contact_method, "decision_maker": decision_maker,
        "last_visited_at": last_visited_at, "best_visit_time": best_visit_time,
        "visit_duration": visit_duration, "first_impression": first_impression,
        "last_impression": last_impression, "materials_left": materials_left,
        "followup_promised": followup_promised, "access_notes": access_notes,
        "space_notes": space_notes, "price_sensitivity": price_sensitivity, "notes": notes,
    }
    _persist_contact_edit(contact_id, text_fields, fit_score)
    log_audit(None, None, "contact.edited", f"contact:{contact_id}", "updated")
    return RedirectResponse(url=f"/contacts/{contact_id}?saved=1", status_code=303)


@router.post("/{contact_id}/delete")
def delete_contact(contact_id: int, request: Request, _admin: str = Depends(require_admin)):
    if not erase_contact(contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)


@router.post("/{contact_id}/unflag")
def unflag_contact(contact_id: int, request: Request, _admin: str = Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET flagged = FALSE WHERE id = %s", (contact_id,))
    log_audit(None, None, "contact.unflagged", f"contact:{contact_id}", "updated")
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
    log_audit(None, None, "contact.star_changed", f"contact:{contact_id}", str(starred).lower())
    return templates.TemplateResponse(
        "partials/star_button.html",
        {"request": request, "c": {"id": contact_id, "starred": starred}},
    )
