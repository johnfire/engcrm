"""
Run the enrichment agent standalone for a specific city (or globally).

Usage:
    uv run python -m gcrm.supervisor.run_enrichment --city Augsburg
    uv run python -m gcrm.supervisor.run_enrichment --city Augsburg --limit 50
    uv run python -m gcrm.supervisor.run_enrichment --limit 50
"""
import argparse
import functools
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run enrichment agent for a city or globally")
    parser.add_argument("--city", default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from gcrm_enrichment_agent import create_enrichment_agent

    from gcrm.config import CHEAP_LLM
    from gcrm.tools import (
        fetch_page,
        finish_run,
        get_contacts_needing_enrichment,
        get_llm,
        start_run,
        update_contact_details,
        web_search,
    )

    fetch_fn = (
        functools.partial(get_contacts_needing_enrichment, city=args.city)
        if args.city else get_contacts_needing_enrichment
    )

    agent = create_enrichment_agent(
        llm=get_llm(CHEAP_LLM),
        web_search=web_search,
        fetch_page=fetch_page,
        fetch_contacts=fetch_fn,
        update_contact=update_contact_details,
        start_run=start_run,
        finish_run=finish_run,
    )

    city_label = args.city or "all cities"
    logger.info("enrichment: running for %s (limit=%d)", city_label, args.limit)
    result = agent.invoke({"limit": args.limit})
    logger.info("Done: %s", result.get("summary", ""))


if __name__ == "__main__":
    main()
