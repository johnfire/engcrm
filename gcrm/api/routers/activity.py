from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from gcrm.db.connection import db

router = APIRouter(prefix="/activity", tags=["activity"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))


@router.get("/", response_class=HTMLResponse)
def activity_feed(request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, agent_name, started_at, finished_at, status, summary
            FROM agent_runs
            ORDER BY started_at DESC
            LIMIT 500
        """)
        runs = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'pending')   AS pending,
                   COUNT(*) FILTER (WHERE status = 'approved')  AS approved,
                   COUNT(*) FILTER (WHERE status = 'rejected')  AS rejected,
                   COUNT(*) FILTER (WHERE status = 'edited')    AS edited
            FROM approval_queue
        """)
        queue_stats = dict(cur.fetchone())

    return templates.TemplateResponse("activity.html", {
        "request": request,
        "runs": runs,
        "queue_stats": queue_stats,
    })
