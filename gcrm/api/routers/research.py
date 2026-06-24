from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from gcrm.api.templates import templates
from gcrm.tools.db import get_all_city_scan_status
from gcrm.vertical import SCAN_LEVELS
from gcrm.api.auth import require_login, require_admin
from gcrm.supervisor.pipeline import spawn_stage

router = APIRouter(dependencies=[Depends(require_login)])

LEVEL_LABELS = {lvl: cfg["label"] for lvl, cfg in SCAN_LEVELS.items()}


@router.get("/research/", response_class=HTMLResponse)
def research_page(request: Request, queued: str = "", error: str = "", city: str = ""):
    cities = get_all_city_scan_status()

    # Build per-city level map (scan + emailed count) for easy template access
    for city in cities:
        scans_by_level = {scan["level"]: scan for scan in (city["scans"] or [])}
        emailed = city.get("emailed_by_level") or {}
        city["levels"] = [
            {"scan": scans_by_level.get(lvl), "emailed": int(emailed.get(str(lvl), 0))}
            for lvl in SCAN_LEVELS
        ]
        city["emailed_total"] = sum(int(value) for value in emailed.values())
        city["total_contacts"] = city.get("total_contacts") or 0
        city["scanned_levels"] = len(city["scans"] or [])

    total = len(cities)
    level1_done = sum(1 for city in cities if any((level["scan"] or {}).get("level") == 1 for level in city["levels"]))
    unscanned = sum(1 for city in cities if not city["scans"])
    totals = {
        "contacts": sum(city["total_contacts"] for city in cities),
        "emailed": sum(city["emailed_total"] for city in cities),
    }

    return templates.TemplateResponse("research.html", {
        "request": request,
        "cities": cities,
        "level_labels": LEVEL_LABELS,
        "total": total,
        "level1_done": level1_done,
        "unscanned": unscanned,
        "totals": totals,
        "levels": list(SCAN_LEVELS.keys()),
        "queued": queued,
        "error": error,
        "ran_city": city,
    })


@router.post("/research/run")
def research_run(
    stage: str = Form(...),
    city: str = Form(""),
    level: int = Form(1),
    country: str = Form("DE"),
    _role: str = Depends(require_admin),
):
    """Trigger a pipeline stage from the web research page (admin only)."""
    try:
        spawn_stage(stage, city=city, level=level, country=country)
    except ValueError as error:
        return RedirectResponse(
            url=f"/research/?error={quote(str(error))}&city={quote(city)}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/research/?queued={quote(stage)}&city={quote(city)}",
        status_code=303,
    )
