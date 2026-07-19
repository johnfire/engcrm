import logging

from langgraph.graph import END, StateGraph

from .protocols import (
    AgentMission,
    ContactSaver,
    GeoSearcher,
    LanguageModel,
    PageFetcher,
    RunFinisher,
    RunStarter,
    WebSearcher,
)
from .state import ResearchState

logger = logging.getLogger(__name__)


def create_research_agent(
    llm: LanguageModel,
    web_search: WebSearcher,
    geo_search: GeoSearcher,
    fetch_page: PageFetcher,
    save_contact: ContactSaver,
    start_run: RunStarter,
    finish_run: RunFinisher,
    mission: AgentMission,
    get_existing_names=None,
    cutoff: int = 25,
):
    """Build the research graph from module-level dependency-injected nodes."""
    from functools import partial
    from types import SimpleNamespace

    from . import nodes

    dependencies = SimpleNamespace(
        llm=llm,
        web_search=web_search,
        geo_search=geo_search,
        fetch_page=fetch_page,
        save_contact=save_contact,
        start_run=start_run,
        finish_run=finish_run,
        mission=mission,
        get_existing_names=get_existing_names,
        cutoff=cutoff,
    )
    names = (
        "init",
        "run_maps_search",
        "select_new_chunk",
        "run_web_search",
        "fetch_pages",
        "extract_contacts",
        "fetch_missing_emails",
        "save_contacts",
        "generate_report",
    )
    graph = StateGraph(ResearchState)
    for name in names:
        graph.add_node(name, partial(getattr(nodes, name), dependencies=dependencies))
    graph.set_entry_point("init")
    for source, target in zip(names, names[1:]):
        graph.add_edge(source, target)
    graph.add_edge("generate_report", END)
    return graph.compile()
