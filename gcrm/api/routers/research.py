from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from gcrm.tools.db import get_all_city_scan_status

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))

LEVEL_LABELS = {
    1: "Galleries / Cafes / Designers / Coworking",
    2: "Gift / Esoteric / Concept Stores",
    3: "Restaurants",
    4: "Corporate Offices",
    5: "Hotels",
}


@router.get("/research/", response_class=HTMLResponse)
def research_page(request: Request):
    cities = get_all_city_scan_status()

    # Build per-city level map for easy template access
    for c in cities:
        scans_by_level = {s["level"]: s for s in (c["scans"] or [])}
        c["levels"] = [scans_by_level.get(lvl) for lvl in range(1, 6)]
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
        "levels": range(1, 6),
    })
