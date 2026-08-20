"""Mobile area-scan triggers — map-picked or GPS-radius circle scans, the
area equivalent of api_research.py's city scans."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gcrm.api.jwt_auth import require_jwt, require_jwt_payload
from gcrm.supervisor.pipeline import spawn_area_stage
from gcrm.tools.db import add_city
from gcrm.tools.db_areas import build_area_overview, find_or_create_area, get_area_organizations
from gcrm.tools.db_audit import log_audit
from gcrm.tools.search import reverse_geocode

router = APIRouter(prefix="/api/areas", tags=["mobile-areas"])


class AreaScanRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: int = Field(ge=100, le=2000)
    levels: list[int]
    label: str = ""


@router.get("/")
def list_areas(_role: str = Depends(require_jwt)) -> dict:
    """Per-area scan-status list plus headline stats — the read-side mirror of
    the web areas page. Any authenticated user may view it."""
    return build_area_overview()


@router.get("/{area_id}/organizations")
def area_organizations(area_id: int, _role: str = Depends(require_jwt)) -> dict:
    """Contacts currently within the area's radius, for map pins."""
    return {"organizations": get_area_organizations(area_id)}


@router.post("/scan", status_code=202)
def scan_area(
    body: AreaScanRequest,
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    city_id = None
    resolved = reverse_geocode(body.lat, body.lon)
    if resolved and resolved["name"]:
        city_id = add_city(resolved["name"], resolved["country"] or "DE", resolved.get("state", ""))

    area_id = find_or_create_area(body.lat, body.lon, body.radius_m, label=body.label, city_id=city_id)
    try:
        spawn_area_stage("research", area_id, body.levels)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_audit(None, None, "pipeline.area_scan_queued", f"area:{area_id}", ",".join(map(str, body.levels)))
    return {"status": "queued", "area_id": area_id, "levels": body.levels}
