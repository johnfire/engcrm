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


def scout(limit: int = 100, city: str | None = None, linkedin: bool = False, skip_scoring: bool = False) -> str:
    """Judge candidates (all, one city's, or LinkedIn employers'). Returns the run summary."""
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

    if skip_scoring:
        logger.info("scout: LLM scoring disabled — all candidates will be auto-promoted to cold")
    pool = functools.partial(get_candidates, source="linkedin") if linkedin else get_candidates

    def fetch_candidates(limit):
        rows = pool(limit=limit)
        # get_candidates has no city parameter; filter the returned batch in-process.
        return [row for row in rows if not city or (row.get("city") or "").lower() == city.lower()]

    agent = create_scout_agent(
        llm=get_llm(CHEAP_LLM),
        fetch_candidates=fetch_candidates,
        set_organization_state=set_organization_state,
        fetch_page=fetch_page,
        fetch_city_context=get_city_market_context,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        skip_scoring=skip_scoring,
    )
    logger.info("scout: running for %s (limit=%d)", city or "all cities", limit)
    summary = agent.invoke({"limit": limit}).get("summary", "")
    logger.info("Done: %s", summary)
    return summary


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
        dest="skip_scoring",
        action="store_true",
        help="Promote all candidates to ready without LLM scoring",
    )
    args = parser.parse_args()
    scout(args.limit, city=args.city, linkedin=args.linkedin, skip_scoring=args.skip_scoring)


if __name__ == "__main__":
    main()
