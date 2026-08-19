"""Run opportunity analysis for contacts that do not yet have one.

Usage:
    uv run python -m gcrm.supervisor.run_opportunity_analysis
    uv run python -m gcrm.supervisor.run_opportunity_analysis --limit 100
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Analyse unmet custom AI/software opportunities")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from gcrm_opportunity_agent import create_opportunity_agent

    from gcrm.config import ACTIVE_MISSION, CHEAP_LLM, RESEARCH_DOSSIER_ENABLED
    from gcrm.research import get_or_create_dossier
    from gcrm.tools import (
        fetch_page,
        finish_run,
        get_contact_interactions,
        get_contacts_needing_opportunity_analysis,
        get_llm,
        save_opportunity_analysis,
        start_run,
    )

    agent = create_opportunity_agent(
        llm=get_llm(CHEAP_LLM),
        fetch_contacts=get_contacts_needing_opportunity_analysis,
        fetch_interactions=get_contact_interactions,
        fetch_page=fetch_page,
        get_or_create_dossier=get_or_create_dossier if RESEARCH_DOSSIER_ENABLED else None,
        save_analysis=save_opportunity_analysis,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        model_name=CHEAP_LLM,
    )
    logger.info("opportunity analysis: running for up to %d unanalysed contacts", args.limit)
    result = agent.invoke({"limit": args.limit})
    logger.info("Done: %s", result.get("summary", ""))


if __name__ == "__main__":
    main()
