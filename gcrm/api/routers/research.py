from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from gcrm.api.templates import templates
from gcrm.tools.db import get_all_city_scan_status
from gcrm.vertical import SCAN_LEVELS
from gcrm.api.auth import require_login

router = APIRouter(dependencies=[Depends(require_login)])

LEVEL_LABELS = {lvl: cfg["label"] for lvl, cfg in SCAN_LEVELS.items()}


@router.get("/research/", response_class=HTMLResponse)
def research_page(request: Request):
    cities = get_all_city_scan_status()

    # Build per-city level map (scan + emailed count) for easy template access
    for c in cities:
        scans_by_level = {s["level"]: s for s in (c["scans"] or [])}
        emailed = c.get("emailed_by_level") or {}
        c["levels"] = [
            {"scan": scans_by_level.get(lvl), "emailed": int(emailed.get(str(lvl), 0))}
            for lvl in SCAN_LEVELS
        ]
        c["emailed_total"] = sum(int(v) for v in emailed.values())
        c["total_contacts"] = c.get("total_contacts") or 0
        c["scanned_levels"] = len(c["scans"] or [])

    total = len(cities)
    level1_done = sum(1 for c in cities if any((l["scan"] or {}).get("level") == 1 for l in c["levels"]))
    unscanned = sum(1 for c in cities if not c["scans"])
    totals = {
        "contacts": sum(c["total_contacts"] for c in cities),
        "emailed": sum(c["emailed_total"] for c in cities),
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
    })
