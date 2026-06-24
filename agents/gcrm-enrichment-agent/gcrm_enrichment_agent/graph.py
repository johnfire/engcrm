"""
LangGraph enrichment agent.

Fetches contacts that are missing website or email, searches the web for each,
fetches the business's own candidate pages (emails live on Impressum/Kontakt
pages, not in search snippets), and writes whatever it finds — without ever
overwriting data the contact already has.

Pipeline position: research → enrich → scout → outreach → followup
"""
import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from .protocols import (
    LanguageModel,
    WebSearcher,
    PageFetcher,
    ContactFetcher,
    ContactUpdater,
    RunStarter,
    RunFinisher,
)
from .state import EnrichmentState
from .prompts import build_search_query, enrich_contact_prompt
from ._utils import parse_json_response

logger = logging.getLogger(__name__)

# Domains that are directories / maps / social — not the business's own site.
# We skip fetching these because they won't carry the business's real email.
_SKIP_FETCH_DOMAINS = re.compile(
    r"(google\.|facebook\.|instagram\.|yelp\.|tripadvisor\.|gelbeseiten\.|"
    r"yellowpages\.|booking\.|maps\.|wikipedia\.|openstreetmap\.)",
    re.IGNORECASE,
)


def _candidate_urls(search_results: list[dict]) -> list[str]:
    """
    Pick URLs from search results that are likely the business's own website.
    Returns up to 2, skipping known directory/social domains.
    """
    candidates = []
    for result in search_results:
        url = result.get("url", "")
        if url and not _SKIP_FETCH_DOMAINS.search(url):
            candidates.append(url)
        if len(candidates) >= 2:
            break
    return candidates


def create_enrichment_agent(
    llm: LanguageModel,
    web_search: WebSearcher,
    fetch_page: PageFetcher,
    fetch_contacts: ContactFetcher,
    update_contact: ContactUpdater,
    start_run: RunStarter,
    finish_run: RunFinisher,
):
    """
    Build and return a compiled LangGraph enrichment agent.

    Usage:
        agent = create_enrichment_agent(llm=..., web_search=..., fetch_page=..., ...)
        result = agent.invoke({"limit": 50})
        print(result["summary"])
    """

    def init(state: EnrichmentState) -> dict:
        run_id = start_run("enrichment_agent", {"limit": state.get("limit", 50)})
        return {
            "run_id": run_id,
            "limit": state.get("limit", 50),
            "contacts": [],
            "results": [],
            "errors": [],
            "enriched_count": 0,
            "not_found_count": 0,
            "summary": "",
        }

    def fetch(state: EnrichmentState) -> dict:
        try:
            contacts = fetch_contacts(limit=state["limit"])
        except Exception as error:
            return {"errors": state["errors"] + [f"fetch failed: {error}"], "contacts": []}
        logger.info("enrichment: fetched %d contacts needing enrichment", len(contacts))
        return {"contacts": contacts}

    def enrich_all(state: EnrichmentState) -> dict:
        if not state.get("contacts"):
            return {"results": []}

        results = []
        for contact in state["contacts"]:
            name = contact["name"]
            city = contact["city"]
            contact_id = contact["id"]
            # Track what was actually missing so we never overwrite existing data later.
            missing_website = not contact.get("website")
            missing_email = not contact.get("email")
            missing_phone = not contact.get("phone")

            query = build_search_query(contact)

            try:
                search_results = web_search(query=query)
            except Exception as error:
                logger.warning("enrichment: search failed for %s — %s", name, error)
                results.append({"contact_id": contact_id, "found": False})
                continue

            if not search_results:
                results.append({"contact_id": contact_id, "found": False})
                continue

            # Fetch candidate pages — snippets rarely contain the real email.
            page_texts = []
            for url in _candidate_urls(search_results):
                try:
                    text = fetch_page(url)
                    if text:
                        page_texts.append(f"[Page: {url}]\n{text[:2000]}")
                except Exception:
                    pass

            # Ask LLM to extract website/email/phone from snippets + page content.
            system, user = enrich_contact_prompt(contact, search_results, page_texts)
            try:
                response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
                data = parse_json_response(response.content)
                website = (data.get("website") or "").strip() or None
                email = (data.get("email") or "").strip() or None
                phone = (data.get("phone") or "").strip() or None
                # "found" means we have new data for a field that was actually missing.
                found = bool(
                    (missing_website and website)
                    or (missing_email and email)
                    or (missing_phone and phone)
                )
                results.append({
                    "contact_id": contact_id,
                    "website": website,
                    "email": email,
                    "phone": phone,
                    "missing_website": missing_website,
                    "missing_email": missing_email,
                    "missing_phone": missing_phone,
                    "found": found,
                })
                if found:
                    logger.info("enrichment: found data for %s / %s — %s %s", name, city, website, email)
                else:
                    logger.debug("enrichment: nothing new for %s / %s", name, city)
            except Exception as error:
                logger.warning("enrichment: LLM extraction failed for %s — %s", name, error)
                results.append({"contact_id": contact_id, "found": False})

        return {"results": results}

    def apply_results(state: EnrichmentState) -> dict:
        enriched = 0
        not_found = 0
        for result in state.get("results", []):
            contact_id = result.get("contact_id")
            # Only write fields that were actually missing — never overwrite existing data.
            updates = {}
            if result.get("missing_website") and result.get("website"):
                updates["website"] = result["website"]
            if result.get("missing_email") and result.get("email"):
                updates["email"] = result["email"]
            if result.get("missing_phone") and result.get("phone"):
                updates["phone"] = result["phone"]

            try:
                if updates:
                    update_contact(contact_id=contact_id, **updates)
                    enriched += 1
                else:
                    # Nothing usable found — mark as a dead-end so we stop retrying it.
                    # update_contact always stamps enriched_at, so it counts as processed.
                    not_found += 1
                    update_contact(contact_id=contact_id, status="cannot_find_more_data")
            except Exception as error:
                logger.warning("enrichment: update failed for contact %s — %s", contact_id, error)
        return {"enriched_count": enriched, "not_found_count": not_found}

    def generate_report(state: EnrichmentState) -> dict:
        enriched = state.get("enriched_count", 0)
        not_found = state.get("not_found_count", 0)
        total = len(state.get("contacts", []))
        errs = state.get("errors", [])
        summary = (
            f"enrichment_agent: processed {total} contacts — "
            f"{enriched} enriched, {not_found} not found"
        )
        if errs:
            summary += f", {len(errs)} error(s)"
        finish_run(
            state.get("run_id", 0),
            "completed",
            summary,
            {"total": total, "enriched": enriched, "not_found": not_found},
        )
        return {"summary": summary}

    graph = StateGraph(EnrichmentState)
    graph.add_node("init", init)
    graph.add_node("fetch", fetch)
    graph.add_node("enrich_all", enrich_all)
    graph.add_node("apply_results", apply_results)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "enrich_all")
    graph.add_edge("enrich_all", "apply_results")
    graph.add_edge("apply_results", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
