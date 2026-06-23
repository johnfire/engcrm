"""Mobile activity feed (recent agent runs)."""
from fastapi import APIRouter, Depends

from gcrm.api.jwt_auth import require_jwt
from gcrm.db.connection import db

router = APIRouter(prefix="/api/activity", tags=["mobile-activity"])


@router.get("")
def list_activity(_role: str = Depends(require_jwt)) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, agent_name, status, summary, started_at, finished_at
            FROM agent_runs
            ORDER BY started_at DESC
            LIMIT 50
            """
        )
        rows = []
        for row in cur.fetchall():
            r = dict(row)
            r["started_at"] = r["started_at"].isoformat() if r["started_at"] else None
            r["finished_at"] = r["finished_at"].isoformat() if r["finished_at"] else None
            rows.append(r)
        return rows
