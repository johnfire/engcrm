"""Mobile pipeline triggers — run a single stage (or the whole city pipeline)
for a selected city + level. Each run logs to agent_runs, so progress shows on
the Activity screen."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin
from gcrm.supervisor.pipeline import spawn_stage
from gcrm.tools.db_audit import log_audit

router = APIRouter(prefix="/api/pipeline", tags=["mobile-pipeline"])


class StageRequest(BaseModel):
    city: str = ""
    level: int | None = None
    country: str = "DE"


@router.post("/{stage}/run", status_code=202)
def run_stage(
    stage: str,
    body: StageRequest,
    _role: str = Depends(require_jwt_admin),
) -> dict:
    try:
        spawn_stage(stage, city=body.city, level=body.level, country=body.country)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_audit(None, None, "pipeline.stage_queued", f"pipeline:{stage}", body.city or "global")
    return {"status": "queued", "stage": stage, "city": body.city or None}
