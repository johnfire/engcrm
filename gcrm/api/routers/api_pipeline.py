"""Mobile pipeline triggers — run a single stage (or the whole city pipeline)
for a selected city + level. Each run logs to agent_runs, so progress shows on
the Activity screen."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin
from gcrm.supervisor.pipeline import spawn_stage
from gcrm.tools.db import add_city
from gcrm.tools.db_audit import log_audit
from gcrm.tools.search import normalize_city

router = APIRouter(prefix="/api/pipeline", tags=["mobile-pipeline"])


class StageRequest(BaseModel):
    city: str = ""
    level: int | None = None
    country: str = "DE"
    confirmed: bool = False


# Stages that take no city, so there is nothing to normalize or register.
_GLOBAL_STAGES = {"followup", "opportunity"}


@router.post("/{stage}/run", status_code=202)
def run_stage(
    stage: str,
    body: StageRequest,
    _role: str = Depends(require_jwt_admin),
) -> dict:
    """Queue a stage. For city-scoped stages the typed city is checked against
    Nominatim first, like the web Research page: unless it is already the one
    canonical match, answer 200 `needs_confirmation` with the candidates and let
    the phone resend the chosen name with `confirmed: true`."""
    city = body.city.strip()
    scoped = stage not in _GLOBAL_STAGES and bool(city)
    if scoped and not body.confirmed:
        candidates = normalize_city(city, body.country)
        exact = any(candidate["name"].lower() == city.lower() for candidate in candidates)
        if not exact or len(candidates) > 1:
            return JSONResponse(
                {"status": "needs_confirmation", "typed": city, "candidates": candidates},
                status_code=200,
            )
    try:
        if scoped:
            add_city(city, body.country)
        spawn_stage(stage, city=city, level=body.level, country=body.country)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_audit(None, None, "pipeline.stage_queued", f"pipeline:{stage}", city or "global")
    return {"status": "queued", "stage": stage, "city": city or None}
