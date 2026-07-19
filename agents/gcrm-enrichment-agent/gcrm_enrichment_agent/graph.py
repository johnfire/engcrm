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

from langgraph.graph import END, StateGraph

from .protocols import (
    ContactFetcher,
    ContactUpdater,
    LanguageModel,
    PageFetcher,
    RunFinisher,
    RunStarter,
    WebSearcher,
)
from .state import EnrichmentState

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
    """Build the enrichment graph from module-level dependency-injected nodes."""
    from functools import partial
    from types import SimpleNamespace

    from . import nodes

    dependencies = SimpleNamespace(
        llm=llm,
        web_search=web_search,
        fetch_page=fetch_page,
        fetch_contacts=fetch_contacts,
        update_contact=update_contact,
        start_run=start_run,
        finish_run=finish_run,
    )
    graph = StateGraph(EnrichmentState)
    for name in ("init", "fetch", "enrich_all", "apply_results", "generate_report"):
        graph.add_node(name, partial(getattr(nodes, name), dependencies=dependencies))
    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "enrich_all")
    graph.add_edge("enrich_all", "apply_results")
    graph.add_edge("apply_results", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()
