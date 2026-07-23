from functools import partial
from types import SimpleNamespace

from langgraph.graph import END, StateGraph

from . import nodes
from .state import OpportunityState


def create_opportunity_agent(
    llm,
    fetch_contacts,
    fetch_interactions,
    fetch_page,
    get_or_create_dossier,
    save_analysis,
    start_run,
    finish_run,
    mission,
    model_name: str,
):
    """Build the opportunity-analysis graph with injected infrastructure."""
    dependencies = SimpleNamespace(
        llm=llm,
        fetch_contacts=fetch_contacts,
        fetch_interactions=fetch_interactions,
        fetch_page=fetch_page,
        get_or_create_dossier=get_or_create_dossier,
        save_analysis=save_analysis,
        start_run=start_run,
        finish_run=finish_run,
        mission=mission,
        model_name=model_name,
    )
    graph = StateGraph(OpportunityState)
    for name in ("initialize", "fetch_contacts", "analyse_contacts", "save_analyses", "generate_report"):
        graph.add_node(name, partial(getattr(nodes, name), dependencies=dependencies))
    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "fetch_contacts")
    graph.add_edge("fetch_contacts", "analyse_contacts")
    graph.add_edge("analyse_contacts", "save_analyses")
    graph.add_edge("save_analyses", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()
