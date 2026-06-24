"""Mobile activity feed (recent agent runs)."""
from fastapi import APIRouter, Depends

from gcrm.api.jwt_auth import require_jwt
from gcrm.db.connection import db
from gcrm.tools.db import serialize_row

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
        return [serialize_row(dict(row)) for row in cur.fetchall()]
