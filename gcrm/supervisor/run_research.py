"""
Run the research agent standalone for a city + level(s), or for a map-picked
/ GPS-radius area + level(s).

Usage:
    uv run python -m gcrm.supervisor.run_research --city Konstanz --level 1
    uv run python -m gcrm.supervisor.run_research --city Stuttgart --level 1 --country DE
    uv run python -m gcrm.supervisor.run_research --area-id 7 --levels 1,3,5
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run research agent for a city, or an area, + level(s)")
    parser.add_argument("--city", default=None)
    parser.add_argument("--level", type=int, default=None, help="Single level (city scans)")
    parser.add_argument("--country", default="DE")
    parser.add_argument("--area-id", type=int, default=None, help="Run against a saved scan_areas row instead of a city")
    parser.add_argument("--levels", default=None, help="Comma-separated levels, e.g. 1,3,5 (area scans)")
    args = parser.parse_args()

    from gcrm_research_agent import create_research_agent

    from gcrm.config import ACTIVE_MISSION, CHEAP_LLM, SCAN_CUTOFF
    from gcrm.tools import (
        can_run_level,
        fetch_page,
        finish_run,
        get_area,
        get_existing_organization_names,
        get_llm,
        google_maps_search,
        record_area_scan_result,
        record_scan_result,
        save_organization,
        start_run,
        web_search,
    )
    from gcrm.vertical import SCAN_LEVELS

    if args.area_id is not None:
        area = get_area(args.area_id)
        if not area:
            logger.error("Cannot run: no scan_areas row with id %d", args.area_id)
            return
        levels = [int(level) for level in (args.levels or "1").split(",") if level.strip()]
        city, country = area.get("city") or "", area.get("country") or "DE"
        level_label = ",".join(str(level) for level in levels)
        logger.info(
            "Researching area #%d (%.4f,%.4f r=%dm) — levels %s using %s",
            args.area_id, area["latitude"], area["longitude"], area["radius_m"], level_label, CHEAP_LLM,
        )
        agent = create_research_agent(
            llm=get_llm(CHEAP_LLM),
            web_search=web_search,
            geo_search=google_maps_search,
            fetch_page=fetch_page,
            save_organization=save_organization,
            start_run=start_run,
            finish_run=finish_run,
            mission=ACTIVE_MISSION,
            get_existing_names=get_existing_organization_names,
            cutoff=SCAN_CUTOFF,
        )
        result = agent.invoke({
            "city": city,
            "country": country,
            "levels": levels,
            "area_id": args.area_id,
            "latitude": area["latitude"],
            "longitude": area["longitude"],
            "radius_m": area["radius_m"],
        })
        summary = result.get("summary", "")
        organizations_found = len(result.get("saved_ids", []))
        complete = bool(result.get("scan_complete", False))
        for level in levels:
            record_area_scan_result(args.area_id, level, organizations_found, complete=complete)
        logger.info("Done: %s", summary)
        return

    if not args.city or args.level is None:
        logger.error("Cannot run: --city and --level are required (or use --area-id/--levels)")
        return

    allowed, reason = can_run_level(args.city, args.country, args.level)
    if not allowed:
        logger.error("Cannot run: %s", reason)
        return

    level_label = SCAN_LEVELS[args.level]["label"]
    logger.info("Researching %s — level %d (%s) using %s", args.city, args.level, level_label, CHEAP_LLM)

    agent = create_research_agent(
        llm=get_llm(CHEAP_LLM),
        web_search=web_search,
        geo_search=google_maps_search,
        fetch_page=fetch_page,
        save_organization=save_organization,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        get_existing_names=get_existing_organization_names,
        cutoff=SCAN_CUTOFF,
    )

    result = agent.invoke({
        "city": args.city,
        "country": args.country,
        "levels": [args.level],
    })

    summary = result.get("summary", "")
    organizations_found = len(result.get("saved_ids", []))
    complete = bool(result.get("scan_complete", False))
    record_scan_result(args.city, args.country, args.level, organizations_found, complete=complete)

    if organizations_found > 0:
        from gcrm.tools.memory import capture_thought
        capture_thought(
            f"gcrm city scan: {args.city} (level {args.level}). "
            f"Found {organizations_found} new contacts. {summary}"
        )
        logger.info("memory: captured city observation for %s", args.city)

    logger.info("Done: %s", summary)


if __name__ == "__main__":
    main()
