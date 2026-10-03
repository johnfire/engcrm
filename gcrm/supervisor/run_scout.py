"""
Run the scout agent standalone.

Usage:
    uv run python -m gcrm.supervisor.run_scout
    uv run python -m gcrm.supervisor.run_scout --limit 200
    uv run python -m gcrm.supervisor.run_scout --city Augsburg
    uv run python -m gcrm.supervisor.run_scout --linkedin --limit 25   # organizations from LinkedIn only
    uv run python -m gcrm.supervisor.run_scout --skip-scoring   # promote all candidates to cold, no LLM scoring
"""
import argparse
import functools
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run scout agent")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--city", type=str, default=None, help="Only scout candidates in this city")
    parser.add_argument(
        "--linkedin",
        action="store_true",
        help="Scout only the organizations created from LinkedIn employers (the scheduled "
        "pipeline never does; each one is an LLM call, so start with a small --limit)",
    )
    parser.add_argument(
        "--skip-scoring",
        "--skip-galleries",
        dest="skip_scoring",
        action="store_true",
        help="Promote all candidates to cold without LLM scoring (bypasses SCORED_TYPES)",
    )
    args = parser.parse_args()

    import gcrm_scout_agent.graph as scout_graph
    from gcrm_scout_agent import create_scout_agent

    from gcrm.config import ACTIVE_MISSION, CHEAP_LLM
    from gcrm.tools import (
        fetch_page,
        finish_run,
        get_candidates,
        get_city_market_context,
        get_llm,
        set_organization_state,
        start_run,
    )

    if args.skip_scoring:
        # The scout graph derives SCORED_TYPES_LC at import time; clear both so
        # split_and_promote sees no scored types and auto-promotes everything.
        scout_graph.SCORED_TYPES = set()
        scout_graph.SCORED_TYPES_LC = set()
        scout_graph.ALWAYS_SCORED_SOURCES = set()
        logger.info("scout: LLM scoring disabled — all candidates will be auto-promoted to cold")

    pool = functools.partial(get_candidates, source="linkedin") if args.linkedin else get_candidates

    # get_candidates has no city parameter; filter the returned batch in-process.
    if args.city:
        def fetch_candidates(limit):
            rows = pool(limit=limit)
            return [organization for organization in rows if (organization.get("city") or "").lower() == args.city.lower()]
    else:
        fetch_candidates = pool

    agent = create_scout_agent(
        llm=get_llm(CHEAP_LLM),
        fetch_candidates=fetch_candidates,
        set_organization_state=set_organization_state,
        fetch_page=fetch_page,
        fetch_city_context=get_city_market_context,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
    )

    city_label = args.city or "all cities"
    logger.info("scout: running for %s (limit=%d)", city_label, args.limit)
    result = agent.invoke({"limit": args.limit})
    logger.info("Done: %s", result.get("summary", ""))


if __name__ == "__main__":
    main()
