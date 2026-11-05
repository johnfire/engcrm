"""
Run the research agent standalone for a city + level(s), or for a map-picked
/ GPS-radius area + level(s).

Usage:
    uv run python -m gcrm.supervisor.run_research --city Konstanz --level 1
    uv run python -m gcrm.supervisor.run_research --city Stuttgart --level 1 --country DE
    uv run python -m gcrm.supervisor.run_research --area-id 7 --levels 1,3,5
"""
import argparse
import functools
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def _research_agent():

    from gcrm_research_agent import create_research_agent

    from gcrm import tools
    from gcrm.config import ACTIVE_MISSION, CHEAP_LLM, SCAN_CUTOFF
    from gcrm.sources import RESEARCH_AGENT

    return create_research_agent(
        llm=tools.get_llm(CHEAP_LLM),
        web_search=tools.web_search,
        geo_search=tools.google_maps_search,
        fetch_page=tools.fetch_page,
        save_organization=functools.partial(tools.save_organization, source=RESEARCH_AGENT),
        start_run=tools.start_run,
        finish_run=tools.finish_run,
        mission=ACTIVE_MISSION,
        get_existing_names=tools.get_existing_organization_names,
        cutoff=SCAN_CUTOFF,
    )


def research_area(area_id: int, levels: list[int]) -> list[int]:
    """Research a saved scan area for the given levels. Returns the ids of the new companies."""
    from gcrm import tools
    from gcrm.config import CHEAP_LLM

    area = tools.get_area(area_id)
    if not area:
        raise ValueError(f"no scan_areas row with id {area_id}")
    city, country = area.get("city") or "", area.get("country") or "DE"
    # The area id is enough to find it again; its coordinates stay out of the log.
    logger.info("Researching area #%d (r=%dm) — levels %s using %s",
                area_id, area["radius_m"], ",".join(map(str, levels)), CHEAP_LLM)
    result = _research_agent().invoke({
        "city": city, "country": country, "levels": levels, "area_id": area_id,
        "latitude": area["latitude"], "longitude": area["longitude"], "radius_m": area["radius_m"],
    })
    saved_ids = list(result.get("saved_ids", []))
    complete = bool(result.get("scan_complete", False))
    for level in levels:
        tools.record_area_scan_result(area_id, level, len(saved_ids), complete=complete)
    logger.info("Done: %s", result.get("summary", ""))
    return saved_ids


def research_city(city: str, country: str, level: int) -> list[int]:
    """Research one city at one level. Returns the ids of the new companies."""
    from gcrm import tools
    from gcrm.config import CHEAP_LLM
    from gcrm.vertical import SCAN_LEVELS

    allowed, reason = tools.can_run_level(city, country, level)
    if not allowed:
        raise ValueError(reason)
    logger.info("Researching %s — level %d (%s) using %s", city, level, SCAN_LEVELS[level]["label"], CHEAP_LLM)
    result = _research_agent().invoke({"city": city, "country": country, "levels": [level]})
    summary = result.get("summary", "")
    saved_ids = list(result.get("saved_ids", []))
    tools.record_scan_result(city, country, level, len(saved_ids),
                             complete=bool(result.get("scan_complete", False)))
    if saved_ids:
        from gcrm.tools.memory import capture_thought
        capture_thought(f"gcrm city scan: {city} (level {level}). Found {len(saved_ids)} new contacts. {summary}")
        logger.info("memory: captured city observation for %s", city)
    logger.info("Done: %s", summary)
    return saved_ids


def main():
    parser = argparse.ArgumentParser(description="Run research agent for a city, or an area, + level(s)")
    parser.add_argument("--city", default=None)
    parser.add_argument("--level", type=int, default=None, help="Single level (city scans)")
    parser.add_argument("--country", default="DE")
    parser.add_argument("--area-id", type=int, default=None, help="Run against a saved scan_areas row instead of a city")
    parser.add_argument("--levels", default=None, help="Comma-separated levels, e.g. 1,3,5 (area scans)")
    args = parser.parse_args()

    try:
        if args.area_id is not None:
            research_area(args.area_id, [int(level) for level in (args.levels or "1").split(",") if level.strip()])
        elif args.city and args.level is not None:
            research_city(args.city, args.country, args.level)
        else:
            logger.error("Cannot run: --city and --level are required (or use --area-id/--levels)")
    except ValueError as error:
        logger.error("Cannot run: %s", error)


if __name__ == "__main__":
    main()
