"""Mobile research trigger — kicks off a city scan or generates a dossier."""
import subprocess
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_payload
from gcrm.research import get_or_create_dossier
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


@router.get("/dossier/{contact_id}")
def get_dossier(contact_id: int, _role: str = Depends(require_jwt)) -> dict:
    """Retrieve an existing research dossier for a contact.
    Returns the dossier or 404 if none exists."""
    dossier = get_or_create_dossier(contact_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="No dossier available for this contact")
    return {"status": "ok", "dossier": dossier}


@router.post("/dossier/{contact_id}", status_code=202)
def generate_dossier(
    contact_id: int,
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    """Generate a research dossier for a single contact (admin only).
    Synchronous — returns the dossier immediately."""
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    dossier = get_or_create_dossier(contact_id)
    if dossier is None:
        raise HTTPException(status_code=422, detail="No website or all sources blocked")
    log_audit(None, None, "research.dossier_generated", f"contact:{contact_id}",
              dossier.get("research_status", "unknown"))
    return {"status": "ok", "dossier": dossier}
