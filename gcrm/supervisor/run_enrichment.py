"""
Run the enrichment agent standalone for a specific city (or globally), or for the companies
a Gather run just found.

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


def build_enrichment_agent(fetch_organizations, llm=None):
    """The one place the enrichment agent is put together with its real tools."""
    from gcrm_enrichment_agent import create_enrichment_agent

    from gcrm import tools
    from gcrm.config import CHEAP_LLM

    return create_enrichment_agent(
        llm=llm or tools.get_llm(CHEAP_LLM),
        web_search=tools.web_search,
        fetch_page=tools.fetch_page,
        fetch_organizations=fetch_organizations,
        update_organization=tools.update_organization_details,
        set_suppression_flag=tools.set_suppression_flag,
        start_run=tools.start_run,
        finish_run=tools.finish_run,
        save_company_pages=tools.save_company_pages,
    )


def enrich_ids(ids: list[int]) -> str:
    """Enrich exactly these companies (a Gather run's new ones). Returns the run summary."""
    from gcrm import tools

    fetch = functools.partial(tools.get_organizations_needing_enrichment, ids=list(ids))
    result = build_enrichment_agent(fetch).invoke({"limit": len(ids)})
    return result.get("summary", "")


def main():
    parser = argparse.ArgumentParser(description="Run enrichment agent for a city or globally")
    parser.add_argument("--city", default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from gcrm import tools

    fetch = (
        functools.partial(tools.get_organizations_needing_enrichment, city=args.city)
        if args.city else tools.get_organizations_needing_enrichment
    )
    city_label = args.city or "all cities"
    logger.info("enrichment: running for %s (limit=%d)", city_label, args.limit)
    result = build_enrichment_agent(fetch).invoke({"limit": args.limit})
    logger.info("Done: %s", result.get("summary", ""))


if __name__ == "__main__":
    main()
