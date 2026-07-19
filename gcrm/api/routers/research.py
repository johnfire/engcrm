from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.templates import templates
from gcrm.supervisor.pipeline import spawn_stage
from gcrm.tools.db import add_city, build_research_overview
from gcrm.tools.db_audit import log_audit
from gcrm.tools.search import normalize_city

router = APIRouter(dependencies=[Depends(require_login)])


def _city_table_context(request: Request) -> dict:
    """Build the per-city scan-status table context shared by the page + the
    city-confirm render. The data shaping lives in build_research_overview() so
    the web page and the mobile Research screen stay in lockstep."""
    context = build_research_overview()
    context["request"] = request
    return context


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
    log_audit(None, None, "pipeline.stage_queued", f"pipeline:{stage}", city or "global")
    return RedirectResponse(
        url=f"/research/?queued={quote(stage)}&city={quote(city)}", status_code=303,
    )
