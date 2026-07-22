from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_login
from gcrm.api.templates import templates
from gcrm.db.connection import db

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
