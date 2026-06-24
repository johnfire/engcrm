from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from gcrm.api.templates import templates
from gcrm.tools.db import get_all_city_scan_status, add_city
from gcrm.tools.search import normalize_city
from gcrm.vertical import SCAN_LEVELS
from gcrm.api.auth import require_login, require_admin
from gcrm.supervisor.pipeline import spawn_stage

router = APIRouter(dependencies=[Depends(require_login)])

LEVEL_LABELS = {lvl: cfg["label"] for lvl, cfg in SCAN_LEVELS.items()}


def _city_table_context(request: Request) -> dict:
    """Build the per-city scan-status table context shared by the page + the
    city-confirm render."""
    cities = get_all_city_scan_status()
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
    level1_done = sum(
        1 for city in cities
        if any((level["scan"] or {}).get("level") == 1 for level in city["levels"])
    )
    unscanned = sum(1 for city in cities if not city["scans"])
    totals = {
        "contacts": sum(city["total_contacts"] for city in cities),
        "emailed": sum(city["emailed_total"] for city in cities),
    }
    return {
        "request": request,
        "cities": cities,
        "level_labels": LEVEL_LABELS,
        "total": total,
        "level1_done": level1_done,
        "unscanned": unscanned,
        "totals": totals,
        "levels": list(SCAN_LEVELS.keys()),
    }


@router.get("/research/", response_class=HTMLResponse)
def research_page(request: Request, queued: str = "", error: str = "", city: str = ""):
    context = _city_table_context(request)
    context.update({"queued": queued, "error": error, "ran_city": city, "city_confirm": None})
    return templates.TemplateResponse("research.html", context)


@router.post("/research/run")
def research_run(
    request: Request,
    stage: str = Form(...),
    city: str = Form(""),
    level: int = Form(1),
    country: str = Form("DE"),
    confirmed: str = Form(""),
    _role: str = Depends(require_admin),
):
    """Trigger a pipeline stage (admin only). For city-scoped stages, normalize
    the city via Nominatim and confirm a variant/typo before adding it."""
    city = city.strip()
    if stage != "followup" and city and not confirmed:
        candidates = normalize_city(city, country)
        exact = any(candidate["name"].lower() == city.lower() for candidate in candidates)
        # Confirm unless the typed name is already the single canonical match.
        if not exact or len(candidates) > 1:
            context = _city_table_context(request)
            context.update({
                "queued": "", "error": "", "ran_city": city,
                "city_confirm": {
                    "typed": city, "candidates": candidates,
                    "stage": stage, "level": level, "country": country,
                },
            })
            return templates.TemplateResponse("research.html", context)

    try:
        if stage != "followup" and city:
            add_city(city, country)
        spawn_stage(stage, city=city, level=level, country=country)
    except ValueError as error:
        return RedirectResponse(
            url=f"/research/?error={quote(str(error))}&city={quote(city)}", status_code=303,
        )
    return RedirectResponse(
        url=f"/research/?queued={quote(stage)}&city={quote(city)}", status_code=303,
    )
