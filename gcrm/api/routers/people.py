from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from gcrm.db.connection import db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))


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
        people = [dict(r) for r in cur.fetchall()]

    return templates.TemplateResponse("people.html", {
        "request": request,
        "people": people,
        "query": q,
    })
