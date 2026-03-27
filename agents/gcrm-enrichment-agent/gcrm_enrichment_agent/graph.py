"""
LangGraph enrichment agent.

Fetches contacts that are missing website or email, searches the web for each,
and updates the contact record with whatever it finds.

Pipeline position: research → enrich → scout → outreach → followup
"""
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from .protocols import LanguageModel, WebSearcher, ContactFetcher, ContactUpdater, RunStarter, RunFinisher
from .state import EnrichmentState
from .prompts import enrich_contact_prompt
from ._utils import parse_json_response

logger = logging.getLogger(__name__)


def create_enrichment_agent(
    llm: LanguageModel,
    web_search: WebSearcher,
    fetch_contacts: ContactFetcher,
    update_contact: ContactUpdater,
    start_run: RunStarter,
    finish_run: RunFinisher,
):
    """
    Build and return a compiled LangGraph enrichment agent.

    Usage:
        agent = create_enrichment_agent(llm=..., web_search=..., ...)
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
        except Exception as e:
            return {"errors": state["errors"] + [f"fetch failed: {e}"], "contacts": []}
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

            # Build search query
            query = f"{name} {city} website email contact"

            try:
                search_results = web_search(query=query)
            except Exception as e:
                logger.warning("enrichment: search failed for %s — %s", name, e)
                results.append({"contact_id": contact_id, "found": False})
                continue

            if not search_results:
                results.append({"contact_id": contact_id, "found": False})
                continue

            # Ask LLM to extract website/email/phone
            system, user = enrich_contact_prompt(contact, search_results)
            try:
                response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
                data = parse_json_response(response.content)
                website = (data.get("website") or "").strip()
                email = (data.get("email") or "").strip()
                phone = (data.get("phone") or "").strip()
                found = bool(website or email or phone)
                results.append({
                    "contact_id": contact_id,
                    "website": website or None,
                    "email": email or None,
                    "phone": phone or None,
                    "found": found,
                })
                if found:
                    logger.info("enrichment: found data for %s / %s — %s %s", name, city, website, email)
                else:
                    logger.debug("enrichment: nothing found for %s / %s", name, city)
            except Exception as e:
                logger.warning("enrichment: LLM extraction failed for %s — %s", name, e)
                results.append({"contact_id": contact_id, "found": False})

        return {"results": results}

    def apply_results(state: EnrichmentState) -> dict:
        enriched = 0
        not_found = 0
        for r in state.get("results", []):
            if not r.get("found"):
                not_found += 1
                continue
            try:
                updates = {}
                if r.get("website"):
                    updates["website"] = r["website"]
                if r.get("email"):
                    updates["email"] = r["email"]
                if r.get("phone"):
                    updates["phone"] = r["phone"]
                if updates:
                    update_contact(contact_id=r["contact_id"], **updates)
                    enriched += 1
            except Exception as e:
                logger.warning("enrichment: update failed for contact %d — %s", r["contact_id"], e)
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
