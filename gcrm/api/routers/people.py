from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.api.auth import require_login

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/people/", response_class=HTMLResponse)
def people_list(request: Request, q: str = ""):
    with db() as conn:
        cur = conn.cursor()
        if q:
            cur.execute(
                """
                SELECT * FROM people
                WHERE name ILIKE %s OR email ILIKE %s OR city ILIKE %s
                ORDER BY name ASC
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            )
        else:
            cur.execute("SELECT * FROM people ORDER BY name ASC")
        people = [dict(row) for row in cur.fetchall()]

    return templates.TemplateResponse("people.html", {
        "request": request,
        "people": people,
        "query": q,
    })
