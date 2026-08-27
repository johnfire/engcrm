from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_login
from gcrm.api.templates import templates
from gcrm.db.connection import db

router = APIRouter(prefix="/activity", tags=["activity"], dependencies=[Depends(require_login)])


@router.get("/", response_class=HTMLResponse)
def activity_feed(request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ar.id, ar.agent_name, ar.started_at, ar.finished_at, ar.status, ar.summary,
                   rc.total_usd AS cost_usd
            FROM agent_runs ar
            LEFT JOIN run_costs rc ON rc.run_id = ar.id
            ORDER BY ar.started_at DESC
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

        cur.execute("""
            SELECT
                COALESCE(SUM(total_usd) FILTER (WHERE recorded_at >= CURRENT_DATE), 0) AS today,
                COALESCE(SUM(total_usd) FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days'), 0) AS this_week,
                COALESCE(SUM(total_usd) FILTER (WHERE recorded_at >= NOW() - INTERVAL '30 days'), 0) AS this_month,
                COALESCE(SUM(total_usd), 0) AS all_time
            FROM run_costs
        """)
        spend_stats = dict(cur.fetchone())

        cur.execute("""
            SELECT ar.agent_name,
                   COUNT(*) AS run_count,
                   SUM(rc.total_usd) AS total_usd,
                   AVG(rc.total_usd) AS avg_usd
            FROM run_costs rc
            JOIN agent_runs ar ON ar.id = rc.run_id
            GROUP BY ar.agent_name
            ORDER BY total_usd DESC
        """)
        agent_costs = [dict(row) for row in cur.fetchall()]

        cur.execute("SELECT COUNT(*) AS count FROM contacts WHERE pipeline_stage = 'opportunity'")
        opportunity_count = cur.fetchone()["count"]

    cost_per_opportunity = (
        spend_stats["all_time"] / opportunity_count if opportunity_count else None
    )

    return templates.TemplateResponse("activity.html", {
        "request": request,
        "runs": runs,
        "queue_stats": queue_stats,
        "spend_stats": spend_stats,
        "agent_costs": agent_costs,
        "opportunity_count": opportunity_count,
        "cost_per_opportunity": cost_per_opportunity,
    })
