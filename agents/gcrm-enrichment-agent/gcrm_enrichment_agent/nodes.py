"""Module-level nodes for the enrichment graph."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ._utils import parse_json_response
from .graph import _candidate_urls
from .prompts import build_search_query, enrich_organization_prompt
from .state import EnrichmentState

logger = logging.getLogger(__name__)


def init(state: EnrichmentState, dependencies) -> dict:
    run_id = dependencies.start_run("enrichment_agent", {"limit": state.get("limit", 50)})
    return {
        "run_id": run_id,
        "limit": state.get("limit", 50),
        "organizations": [],
        "results": [],
        "errors": [],
        "enriched_count": 0,
        "not_found_count": 0,
        "summary": "",
    }


def fetch(state: EnrichmentState, dependencies) -> dict:
    try:
        organizations = dependencies.fetch_organizations(limit=state["limit"])
    except Exception as error:
        return {"errors": state["errors"] + [f"fetch failed: {error}"], "organizations": []}
    logger.info("enrichment: fetched %d contacts needing enrichment", len(organizations))
    return {"organizations": organizations}


def enrich_all(state: EnrichmentState, dependencies) -> dict:
    if not state.get("organizations"):
        return {"results": []}
    results = []
    for organization in state["organizations"]:
        name = organization["name"]
        city = organization["city"]
        contact_id = organization["id"]
        missing_website = not organization.get("website")
        missing_email = not organization.get("email")
        missing_phone = not organization.get("phone")
        query = build_search_query(organization)
        known_website = (organization.get("website") or "").strip()
        try:
            search_results = dependencies.web_search(query=query)
        except Exception as error:
            # A search outage must not decide the contact's fate — fall through
            # and read the site we already hold, if there is one.
            logger.warning("enrichment: search failed for %s — %s", name, error)
            search_results = []
        if not search_results and not known_website:
            results.append({"contact_id": contact_id, "found": False})
            continue
        page_texts = []
        for url in _candidate_urls(search_results, known_website):
            try:
                text = dependencies.fetch_page(url)
                if text:
                    page_texts.append(f"[Page: {url}]\n{text[:2000]}")
            except Exception:
                pass
        system, user = enrich_organization_prompt(organization, search_results, page_texts)
        try:
            response = dependencies.llm.invoke(
                [SystemMessage(content=system), HumanMessage(content=user)]
            )
            data = parse_json_response(response.content)
            website = (data.get("website") or "").strip() or None
            email = (data.get("email") or "").strip() or None
            phone = (data.get("phone") or "").strip() or None
            found = bool(
                missing_website
                and website
                or (missing_email and email)
                or (missing_phone and phone)
            )
            results.append(
                {
                    "contact_id": contact_id,
                    "website": website,
                    "email": email,
                    "phone": phone,
                    "missing_website": missing_website,
                    "missing_email": missing_email,
                    "missing_phone": missing_phone,
                    "found": found,
                }
            )
            if found:
                logger.info(
                    "enrichment: found data for %s / %s — %s %s", name, city, website, email
                )
            else:
                logger.debug("enrichment: nothing new for %s / %s", name, city)
        except Exception as error:
            logger.warning("enrichment: LLM extraction failed for %s — %s", name, error)
            results.append({"contact_id": contact_id, "found": False})
    return {"results": results}


def apply_results(state: EnrichmentState, dependencies) -> dict:
    enriched = 0
    not_found = 0
    for result in state.get("results", []):
        contact_id = result.get("contact_id")
        updates = {}
        if result.get("missing_website") and result.get("website"):
            updates["website"] = result["website"]
        if result.get("missing_email") and result.get("email"):
            updates["email"] = result["email"]
        if result.get("missing_phone") and result.get("phone"):
            updates["phone"] = result["phone"]
        try:
            if updates:
                dependencies.update_organization(contact_id=contact_id, **updates)
                enriched += 1
            else:
                not_found += 1
                dependencies.set_suppression_flag(contact_id=contact_id, flag="research_exhausted")
        except Exception as error:
            logger.warning("enrichment: update failed for contact %s — %s", contact_id, error)
    return {"enriched_count": enriched, "not_found_count": not_found}


def generate_report(state: EnrichmentState, dependencies) -> dict:
    enriched = state.get("enriched_count", 0)
    not_found = state.get("not_found_count", 0)
    total = len(state.get("organizations", []))
    errs = state.get("errors", [])
    summary = (
        f"enrichment_agent: processed {total} contacts — {enriched} enriched, {not_found} not found"
    )
    if errs:
        summary += f", {len(errs)} error(s)"
    dependencies.finish_run(
        state.get("run_id", 0),
        "completed",
        summary,
        {"total": total, "enriched": enriched, "not_found": not_found},
    )
    return {"summary": summary}
