"""
Find decision-makers, and their public LinkedIn/XING profiles, for companies the scout
rated ready — by web search only (see gcrm.people_finder).

Usage:
    uv run python -m gcrm.supervisor.run_find_people              # up to 20 companies
    uv run python -m gcrm.supervisor.run_find_people --limit 5
"""
import argparse
import logging

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def find_people_for_ready_companies(limit: int, *, find, fetch_organizations, save_person_found,
                                    mark_searched) -> dict:
    """Search each company in turn; one company failing never stops the others."""
    totals = {"companies": 0, "people": 0, "with_profile": 0, "connections": 0, "errors": 0}
    for organization in fetch_organizations(limit=limit):
        try:
            saved = [save_person_found(organization, person) for person in find(organization)]
            mark_searched(organization["id"])
        except Exception as error:
            logger.warning("find_people: %s failed — %s", organization.get("name"), error)
            totals["errors"] += 1
            continue
        totals["companies"] += 1
        totals["people"] += len(saved)
        totals["with_profile"] += sum(1 for person in saved if person["linkedin_url"] or person["xing_url"])
        totals["connections"] += sum(1 for person in saved if person["is_connection"])
        for person in saved:
            profile = person["linkedin_url"] or person["xing_url"] or "no public profile found"
            known = " — already your LinkedIn connection" if person["is_connection"] else ""
            logger.info("  %s: %s (%s)%s", organization["name"], person["name"], profile, known)
    return totals


def summary_line(totals: dict) -> str:
    return (f"people_finder: {totals['companies']} companies searched — {totals['people']} people found, "
            f"{totals['with_profile']} with a public profile, {totals['connections']} already connections"
            + (f", {totals['errors']} error(s)" if totals["errors"] else ""))


def run(limit: int) -> str:
    from functools import partial

    from gcrm.config import CHEAP_LLM
    from gcrm.people_finder import find_people, llm_extractor
    from gcrm.tools import fetch_page, finish_run, get_llm, start_run, web_search
    from gcrm.tools.db_people_search import (
        get_organizations_needing_people,
        mark_people_searched,
        save_found_person,
    )

    run_id = start_run("people_finder", {"limit": limit})
    find = partial(find_people, search=web_search, fetch_page=fetch_page, extract=llm_extractor(get_llm(CHEAP_LLM)))
    totals = find_people_for_ready_companies(
        limit, find=find, fetch_organizations=get_organizations_needing_people,
        save_person_found=save_found_person, mark_searched=mark_people_searched,
    )
    summary = summary_line(totals)
    finish_run(run_id, "completed", summary, totals)
    return summary


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Find decision-makers for ready companies by web search")
    parser.add_argument("--limit", type=int, default=20, help="Companies to search this run")
    logger.info(run(parser.parse_args().limit))


if __name__ == "__main__":
    main()
