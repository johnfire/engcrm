"""Mobile research trigger — kicks off a city scan in the background."""
import subprocess
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_payload
from gcrm.tools.db import build_research_overview
from gcrm.tools.db_audit import log_audit
from gcrm.vertical import SCAN_LEVELS

router = APIRouter(prefix="/api/research", tags=["mobile-research"])


class ResearchRequest(BaseModel):
    city: str
    level: int
    country: str = "DE"


@router.get("/overview")
def research_overview(_role: str = Depends(require_jwt)) -> dict:
    """Per-city scan-status table plus headline stats — the read-side mirror of
    the web Research page. Any authenticated user may view it."""
    return build_research_overview()


def _run_research(city: str, level: int, country: str) -> None:
    subprocess.Popen(
        [sys.executable, "-m", "gcrm.supervisor.run_research",
         "--city", city, "--level", str(level), "--country", country],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@router.post("/run", status_code=202)
def run_research(
    body: ResearchRequest,
    background_tasks: BackgroundTasks,
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if body.level not in SCAN_LEVELS:
        raise HTTPException(status_code=422, detail=f"Level must be one of {sorted(SCAN_LEVELS)}")
    background_tasks.add_task(_run_research, body.city, body.level, body.country)
    log_audit(None, None, "pipeline.research_queued", f"city:{body.country}:{body.city}", f"level:{body.level}")
    return {"status": "queued", "city": body.city, "level": body.level}
