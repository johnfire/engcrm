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
    SuppressionFlagSetter,
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


MAX_FETCHES = 3


def _impressum_url(website: str) -> str:
    """German law requires an Impressum, and it is where the real contact address
    lives — a far better target than a homepage footer."""
    return website.rstrip("/") + "/impressum"


def _candidate_urls(search_results: list[dict], known_website: str = "") -> list[str]:
    """
    URLs likely to carry the business's own contact details, best first.

    A website we already hold leads, together with its Impressum: a small trade
    business is often invisible to web search while its contact address sits on
    its own site. Relying on search alone meant those contacts were written off
    as unreachable without anyone ever opening the page we already knew about.

    Directory and social domains are skipped, and the total is capped so a
    contact cannot cost an unbounded number of fetches.
    """
    candidates = []
    website = (known_website or "").strip()
    if website and not _SKIP_FETCH_DOMAINS.search(website):
        candidates.append(website)
        candidates.append(_impressum_url(website))
    for result in search_results:
        if len(candidates) >= MAX_FETCHES:
            break
        url = result.get("url", "")
        if url and url not in candidates and not _SKIP_FETCH_DOMAINS.search(url):
            candidates.append(url)
    return candidates[:MAX_FETCHES]


def create_enrichment_agent(
    llm: LanguageModel,
    web_search: WebSearcher,
    fetch_page: PageFetcher,
    fetch_contacts: ContactFetcher,
    update_contact: ContactUpdater,
    set_suppression_flag: SuppressionFlagSetter,
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
        set_suppression_flag=set_suppression_flag,
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
