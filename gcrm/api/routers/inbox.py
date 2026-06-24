from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.api.auth import require_login

router = APIRouter(prefix="/inbox", tags=["inbox"], dependencies=[Depends(require_login)])

CLASSIFICATIONS = ("interested", "warm", "not_interested", "not_possible", "opt_out", "other", "skipped")


@router.get("/", response_class=HTMLResponse)
def inbox_list(
    request: Request,
    classification: str = Query(default=""),
    days: int = Query(default=30),
):
    with db() as conn:
        cur = conn.cursor()

        conditions = ["i.processed = TRUE", "i.received_at >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if classification:
            conditions.append("i.classification = %s")
            params.append(classification)
        else:
            conditions.append("(i.classification != 'skipped' OR i.classification IS NULL)")

        where = "WHERE " + " AND ".join(conditions)

        cur.execute(
            f"""
            SELECT
                i.id, i.from_email, i.subject,
                LEFT(i.body, 300) AS body_snippet,
                i.received_at, i.classification, i.classification_reasoning,
                i.visit_when_nearby,
                c.id AS contact_id, c.name AS contact_name,
                c.city, c.status AS contact_status
            FROM inbox_messages i
            LEFT JOIN contacts c ON c.id = i.matched_contact_id
            {where}
            ORDER BY i.received_at DESC
            LIMIT 200
            """,
            params,
        )
        messages = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT classification, COUNT(*) AS cnt
            FROM inbox_messages
            WHERE processed = TRUE AND received_at >= NOW() - INTERVAL '%s days'
              AND (classification != 'skipped' OR classification IS NULL)
            GROUP BY classification
            ORDER BY cnt DESC
            """,
            (days,),
        )
        counts = {r["classification"]: r["cnt"] for r in cur.fetchall()}
        total = sum(counts.values())

    return templates.TemplateResponse("inbox.html", {
        "request": request,
        "messages": messages,
        "counts": counts,
        "total": total,
        "active_classification": classification,
        "days": days,
        "classifications": CLASSIFICATIONS,
    })
