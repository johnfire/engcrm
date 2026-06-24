"""
Run the research agent standalone for a single city + level.

Usage:
    uv run python -m gcrm.supervisor.run_research --city Konstanz --level 1
    uv run python -m gcrm.supervisor.run_research --city Stuttgart --level 1 --country DE
"""
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run research agent for a city + level")
    parser.add_argument("--city", required=True)
    parser.add_argument("--level", type=int, required=True, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--country", default="DE")
    args = parser.parse_args()

    from gcrm.config import ACTIVE_MISSION, CHEAP_LLM
    from gcrm.tools import (
        save_contact, start_run, finish_run,
        record_scan_result, can_run_level,
        web_search, google_maps_search, fetch_page, get_llm,
    )
    from gcrm.vertical import SCAN_LEVELS
    from gcrm_research_agent import create_research_agent

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
        save_contact=save_contact,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
    )

    result = agent.invoke({
        "city": args.city,
        "country": args.country,
        "level": args.level,
    })

    summary = result.get("summary", "")
    contacts_found = len(result.get("saved_ids", []))
    record_scan_result(args.city, args.country, args.level, contacts_found)

    if contacts_found > 0:
        from gcrm.tools.memory import capture_thought
        capture_thought(
            f"gcrm city scan: {args.city} (level {args.level}). "
            f"Found {contacts_found} new contacts. {summary}"
        )
        logger.info("memory: captured city observation for %s", args.city)

    logger.info("Done: %s", summary)


if __name__ == "__main__":
    main()
