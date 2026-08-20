"""Web area-scan page and JSON endpoints — the area equivalent of research.py's
city scans. The page itself is a Leaflet map (pick a point + radius); the map
interaction talks to these endpoints as JSON rather than posting a form."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from gcrm.api.auth import require_admin, require_login
from gcrm.api.templates import templates
from gcrm.supervisor.pipeline import spawn_area_stage
from gcrm.tools.db import add_city
from gcrm.tools.db_areas import build_area_overview, find_or_create_area, get_area_organizations
from gcrm.tools.db_audit import log_audit
from gcrm.tools.search import reverse_geocode

router = APIRouter(dependencies=[Depends(require_login)])


class AreaScanRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: int = Field(ge=100, le=2000)
    levels: list[int]
    label: str = ""


@router.get("/areas/", response_class=HTMLResponse)
def areas_page(request: Request):
    context = build_area_overview()
    context["request"] = request
    return templates.TemplateResponse("areas.html", context)


@router.get("/areas/overview")
def areas_overview() -> dict:
    return build_area_overview()


@router.get("/areas/{area_id}/organizations")
def area_organizations(area_id: int) -> dict:
    return {"organizations": get_area_organizations(area_id)}


@router.post("/areas/scan", status_code=202)
def scan_area(body: AreaScanRequest, _role: str = Depends(require_admin)) -> dict:
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
