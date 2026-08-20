"""
Run the outreach agent standalone for a specific city (or all cold contacts).

Usage:
    uv run python -m gcrm.supervisor.run_outreach --city Augsburg
    uv run python -m gcrm.supervisor.run_outreach --city Augsburg --limit 10
    uv run python -m gcrm.supervisor.run_outreach --limit 5
"""
import argparse
import functools
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run outreach agent for a city or globally")
    parser.add_argument("--city", default=None, help="Filter outreach to a specific city")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--level", type=int, default=None, help="Filter to a specific scan level")
    parser.add_argument("--neighborhood", default=None, help="Filter to a specific neighborhood within a city")
    parser.add_argument("--min-tier", default=None, choices=["normal", "wealthy"], help="Exclude poor-tier neighborhoods (normal=exclude poor, wealthy=only wealthy)")
    args = parser.parse_args()

    from gcrm_outreach_agent import create_outreach_agent

    from gcrm.config import ACTIVE_MISSION, SMART_LLM
    from gcrm.tools import (
        check_compliance,
        fetch_page,
        finish_run,
        get_llm,
        get_organization_interactions,
        get_organizations_ready_for_outreach,
        queue_for_approval,
        start_run,
    )
    from gcrm.tools.memory import search_gcrm_thoughts

    fetch_kwargs: dict = {}
    if args.city:
        fetch_kwargs["city"] = args.city
    if args.level is not None:
        fetch_kwargs["scan_level"] = args.level
    if args.neighborhood:
        fetch_kwargs["neighborhood"] = args.neighborhood
    if args.min_tier:
        fetch_kwargs["min_tier"] = args.min_tier
    fetch_fn = (
        functools.partial(get_organizations_ready_for_outreach, **fetch_kwargs)
        if fetch_kwargs
        else get_organizations_ready_for_outreach
    )

    agent = create_outreach_agent(
        llm=get_llm(SMART_LLM),
        fetch_ready_organizations=fetch_fn,
        fetch_interactions=get_organization_interactions,
        fetch_page=fetch_page,
        check_compliance=check_compliance,
        queue_for_approval=queue_for_approval,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
    )

    learnings = search_gcrm_thoughts("outreach email tone style", limit=5)
    if learnings:
        logger.info("outreach: injecting %d learnings from Open Brain", len(learnings))

    city_label = args.city or "all cities"
    logger.info("outreach: running for %s (limit=%d)", city_label, args.limit)
    result = agent.invoke({"limit": args.limit, "learnings": learnings})
    logger.info("Done: %s", result.get("summary", ""))


if __name__ == "__main__":
    main()
