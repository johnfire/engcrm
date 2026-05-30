from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from gcrm.tools.db import get_all_city_scan_status
from gcrm.vertical import SCAN_LEVELS
from gcrm.api.auth import require_login

router = APIRouter(dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))

LEVEL_LABELS = {lvl: cfg["label"] for lvl, cfg in SCAN_LEVELS.items()}


@router.get("/research/", response_class=HTMLResponse)
def research_page(request: Request):
    cities = get_all_city_scan_status()

    # Build per-city level map for easy template access
    for c in cities:
        scans_by_level = {s["level"]: s for s in (c["scans"] or [])}
        c["levels"] = [scans_by_level.get(lvl) for lvl in SCAN_LEVELS]
        c["total_contacts"] = sum(s["contacts_found"] for s in (c["scans"] or []))
        c["scanned_levels"] = len(c["scans"] or [])

    total = len(cities)
    level1_done = sum(1 for c in cities if any((s or {}).get("level") == 1 for s in c["levels"] if s))
    unscanned = sum(1 for c in cities if not c["scans"])

    return templates.TemplateResponse("research.html", {
        "request": request,
        "cities": cities,
        "level_labels": LEVEL_LABELS,
        "total": total,
        "level1_done": level1_done,
        "unscanned": unscanned,
        "levels": list(SCAN_LEVELS.keys()),
    })
