from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_people import get_person, update_person

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
