from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from gcrm.db.connection import db

router = APIRouter(prefix="/contacts", tags=["contacts"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))

VALID_STATUSES = (
    "candidate", "cold", "contacted", "meeting", "proposal",
    "accepted", "rejected", "dormant", "on_hold", "dropped", "do_not_contact",
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
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    sort: str = Query(default="id"),
    dir: str = Query(default="asc"),
):
    offset = (page - 1) * PAGE_SIZE
    sort_col = SORT_COLUMNS.get(sort, "c.id")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    with db() as conn:
        cur = conn.cursor()

        conditions = []
        params = []
        if status and status in VALID_STATUSES:
            conditions.append("c.status = %s")
            params.append(status)
        if q:
            conditions.append("(lower(c.name) LIKE %s OR lower(c.city) LIKE %s)")
            params += [f"%{q.lower()}%", f"%{q.lower()}%"]

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
                c.email, c.website, c.fit_score, c.notes, c.flagged,
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

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse("contacts.html", {
        "request": request,
        "contacts": contacts,
        "statuses": statuses,
        "active_status": status,
        "query": q,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "sort": sort,
        "dir": dir,
    })


@router.post("/{contact_id}/delete")
def delete_contact(contact_id: int, request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)


@router.post("/{contact_id}/unflag")
def unflag_contact(contact_id: int, request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET flagged = FALSE WHERE id = %s", (contact_id,))
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)
