"""Enrichment keeps every LinkedIn/XING company page it comes across, and searches for
the pages once per company — also for companies whose email we already have."""
from gcrm_enrichment_agent import create_enrichment_agent

from .test_graph import FakeLLM

LINKEDIN_HIT = {"url": "https://de.linkedin.com/company/meile-gmbh", "title": "Meile GmbH | LinkedIn",
                "snippet": "Kabelkonfektion, Untermeitingen"}
XING_HIT = {"url": "https://www.xing.com/pages/meile-gmbh", "title": "Meile GmbH | XING", "snippet": ""}


def run(organizations, results_by_query, save_company_pages=True):
    saved, searched, updates, flags = {}, [], {}, {}

    def web_search(query):
        searched.append(query)
        return results_by_query(query)

    def save(contact_id, linkedin_url=None, xing_url=None):
        saved[contact_id] = {"linkedin_url": linkedin_url, "xing_url": xing_url}

    agent = create_enrichment_agent(
        llm=FakeLLM(['{"website": null, "email": null, "phone": null}']),
        web_search=web_search, fetch_page=lambda url: "",
        fetch_organizations=lambda limit: organizations,
        update_organization=lambda contact_id, **kwargs: updates.setdefault(contact_id, kwargs),
        set_suppression_flag=lambda contact_id, flag, value=True: flags.setdefault(contact_id, flag),
        start_run=lambda name, data: 1, finish_run=lambda *args: None,
        save_company_pages=save if save_company_pages else None,
    )
    return agent.invoke({"limit": 10}), saved, searched, updates, flags


MEILE = {"id": 1, "name": "Meile GmbH", "city": "Untermeitingen", "country": "DE", "email": ""}


def test_a_page_in_the_normal_search_results_is_kept_without_an_extra_search():
    _, saved, searched, _, _ = run([MEILE], lambda query: [LINKEDIN_HIT, XING_HIT])
    assert saved[1] == {"linkedin_url": "https://www.linkedin.com/company/meile-gmbh/",
                        "xing_url": "https://www.xing.com/pages/meile-gmbh"}
    assert len(searched) == 1


def test_a_missing_page_is_searched_for_once():
    def results(query):
        return [LINKEDIN_HIT, XING_HIT] if "LinkedIn" in query else []

    _, saved, searched, _, _ = run([MEILE], results)
    assert len(searched) == 2 and "LinkedIn" in searched[1] and "XING" in searched[1]
    assert saved[1]["linkedin_url"] and saved[1]["xing_url"]


def test_no_page_found_is_still_recorded_as_checked():
    _, saved, _, _, _ = run([MEILE], lambda query: [])
    assert saved[1] == {"linkedin_url": None, "xing_url": None}


def test_a_company_with_both_pages_already_is_not_searched_again():
    known = {**MEILE, "email": "info@meile.de", "linkedin_url": "https://www.linkedin.com/company/a/",
             "xing_url": "https://www.xing.com/pages/a"}
    _, saved, searched, _, _ = run([known], lambda query: [LINKEDIN_HIT])
    assert searched == [] and 1 in saved  # stamped as checked, nothing looked up


def test_a_company_with_an_email_gets_pages_but_no_detail_lookup_and_no_dead_end_flag():
    with_email = {**MEILE, "email": "info@meile.de"}
    result, saved, searched, updates, flags = run([with_email], lambda query: [LINKEDIN_HIT])
    assert updates == {} and flags == {}
    assert saved[1]["linkedin_url"] == "https://www.linkedin.com/company/meile-gmbh/"


def test_a_found_page_keeps_the_company_from_being_written_off():
    _, _, _, _, flags = run([MEILE], lambda query: [LINKEDIN_HIT])
    assert flags == {}


def test_without_a_page_store_enrichment_works_as_before():
    _, saved, searched, _, flags = run([MEILE], lambda query: [], save_company_pages=False)
    assert saved == {} and len(searched) == 1 and flags == {1: "research_exhausted"}
