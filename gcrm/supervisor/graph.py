"""
LangGraph supervisor that orchestrates all agents in sequence.
Uses a PostgreSQL checkpointer so runs survive crashes and can be resumed.

Run order per invocation:
  1. research_agent    — once per target in RESEARCH_TARGETS
  2. enrichment_agent  — fills in missing website/email for existing contacts
  3. scout_agent       — scores all candidates
  4. opportunity_agent — recommends evidence-backed custom AI/software offers
  5. outreach_agent    — drafts first-contact emails for cold contacts
  6. followup_agent    — processes inbox + sends follow-ups to overdue contacts

Each agent handles the "nothing to do" case gracefully, so the supervisor
always runs to completion even when there is no work.
"""
import logging
from datetime import datetime, timezone
from functools import partial
from typing import TypedDict

from gcrm_enrichment_agent import create_enrichment_agent
from gcrm_followup_agent import create_followup_agent
from gcrm_opportunity_agent import create_opportunity_agent
from gcrm_outreach_agent import create_outreach_agent
from gcrm_research_agent import create_research_agent
from gcrm_scout_agent import create_scout_agent
from langgraph.graph import END, StateGraph

from gcrm.config import ACTIVE_MISSION, CHEAP_LLM, RESEARCH_DOSSIER_ENABLED, SCAN_CUTOFF, SMART_LLM
from gcrm.research import get_or_create_dossier
from gcrm.tools import (
    can_run_level,
    check_compliance,
    fetch_page,
    finish_run,
    get_candidates,
    get_city_market_context,
    get_contact_interactions,
    get_contacts_needing_enrichment,
    get_contacts_needing_opportunity_analysis,
    get_contacts_ready_for_outreach,
    get_existing_contact_names,
    get_llm,
    get_overdue_contacts,
    google_maps_search,
    log_interaction,
    mark_bad_email,
    match_contact_by_email,
    queue_for_approval,
    read_inbox,
    record_scan_result,
    record_warm_outcome,
    save_contact,
    save_inbox_classification,
    save_opportunity_analysis,
    search_gcrm_thoughts,
    set_contact_state,
    set_opt_out,
    set_visit_when_nearby,
    start_run,
    update_contact_details,
    web_search,
)

logger = logging.getLogger(__name__)


class SupervisorState(TypedDict):
    run_id: int
    research_jobs: list[dict]   # list of {city, country, level}
    research_summaries: list[str]
    enrichment_summary: str
    opportunity_summary: str
    scout_summary: str
    outreach_summary: str
    followup_summary: str
    errors: list[str]
    summary: str


def _build_research_agent(llm):
    return create_research_agent(
        llm=llm,
        web_search=web_search,
        geo_search=google_maps_search,
        fetch_page=fetch_page,
        save_contact=save_contact,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        get_existing_names=get_existing_contact_names,
        cutoff=SCAN_CUTOFF,
    )


def _build_enrichment_agent(llm):
    return create_enrichment_agent(
        llm=llm,
        web_search=web_search,
        fetch_page=fetch_page,
        fetch_contacts=get_contacts_needing_enrichment,
        update_contact=update_contact_details,
        start_run=start_run,
        finish_run=finish_run,
    )


def _build_opportunity_agent(llm):
    return create_opportunity_agent(
        llm=llm,
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


def _build_scout_agent(llm):
    return create_scout_agent(
        llm=llm,
        fetch_candidates=get_candidates,
        set_contact_state=set_contact_state,
        fetch_page=fetch_page,
        fetch_city_context=get_city_market_context,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        get_or_create_dossier=get_or_create_dossier if RESEARCH_DOSSIER_ENABLED else None,
    )


def _build_outreach_agent(llm):
    return create_outreach_agent(
        llm=llm,
        fetch_ready_contacts=get_contacts_ready_for_outreach,
        fetch_interactions=get_contact_interactions,
        fetch_page=fetch_page,
        check_compliance=check_compliance,
        queue_for_approval=queue_for_approval,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
    )


def _build_followup_agent(llm):
    return create_followup_agent(
        llm=llm,
        fetch_inbox=read_inbox,
        match_contact=match_contact_by_email,
        log_interaction=log_interaction,
        set_opt_out=set_opt_out,
        handle_bounce=mark_bad_email,
        set_visit_when_nearby=set_visit_when_nearby,
        save_classification=save_inbox_classification,
        fetch_overdue=get_overdue_contacts,
        queue_for_approval=queue_for_approval,
        record_warm_outcome=record_warm_outcome,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
    )


def _build_agents():
    """Instantiate all agents with concrete tools and the active mission. Each
    agent gets its own LLM instance at the tier it needs (cheap vs smart)."""
    return (
        _build_research_agent(get_llm(CHEAP_LLM)),
        _build_enrichment_agent(get_llm(CHEAP_LLM)),
        _build_opportunity_agent(get_llm(CHEAP_LLM)),
        _build_scout_agent(get_llm(CHEAP_LLM)),
        _build_outreach_agent(get_llm(SMART_LLM)),
        _build_followup_agent(get_llm(SMART_LLM)),
    )


def _init_node(state: SupervisorState) -> dict:
    jobs = state.get("research_jobs", [])
    cities = sorted({job["city"] for job in jobs})
    run_id = start_run("supervisor", {"jobs": len(jobs), "cities": cities})
    logger.info("supervisor: starting run_id=%d — researching: %s", run_id, ", ".join(cities) or "none")
    return {
        "run_id": run_id,
        "research_jobs": jobs,
        "research_summaries": [],
        "enrichment_summary": "",
        "opportunity_summary": "",
        "scout_summary": "",
        "outreach_summary": "",
        "followup_summary": "",
        "errors": [],
        "summary": "",
    }


def _run_research_node(state: SupervisorState, research_agent) -> dict:
    summaries = []
    for job in state.get("research_jobs", []):
        city = job["city"]
        country = job.get("country", "DE")
        level = job.get("level", 1)
        allowed, reason = can_run_level(city, country, level)
        if not allowed:
            msg = f"skipped {city} level {level}: {reason}"
            logger.warning(msg)
            summaries.append(msg)
            continue
        try:
            result = research_agent.invoke({
                "city": city,
                "country": country,
                "level": level,
            })
            summary = result.get("summary", "")
            contacts_found = len(result.get("saved_ids", []))
            complete = bool(result.get("scan_complete", False))
            summaries.append(summary)
            logger.info("research: %s", summary)
            record_scan_result(city, country, level, contacts_found, complete=complete)
        except Exception as error:
            msg = f"research failed for {city} level {level}: {error}"
            logger.error(msg)
            summaries.append(msg)
    return {"research_summaries": summaries}


def _run_enrich_node(state: SupervisorState, enrichment_agent) -> dict:
    try:
        result = enrichment_agent.invoke({"limit": 50})
        logger.info("enrichment: %s", result.get("summary", ""))
        return {"enrichment_summary": result.get("summary", "")}
    except Exception as error:
        msg = f"enrichment failed: {error}"
        logger.error(msg)
        return {"enrichment_summary": msg, "errors": state["errors"] + [msg]}


def _run_scout_node(state: SupervisorState, scout_agent) -> dict:
    try:
        result = scout_agent.invoke({"limit": 100})
        logger.info("scout: %s", result.get("summary", ""))
        return {"scout_summary": result.get("summary", "")}
    except Exception as error:
        msg = f"scout failed: {error}"
        logger.error(msg)
        return {"scout_summary": msg, "errors": state["errors"] + [msg]}


def _run_opportunity_node(state: SupervisorState, opportunity_agent) -> dict:
    try:
        result = opportunity_agent.invoke({"limit": 50})
        logger.info("opportunity analysis: %s", result.get("summary", ""))
        return {"opportunity_summary": result.get("summary", "")}
    except Exception as error:
        msg = f"opportunity analysis failed: {error}"
        logger.error(msg)
        return {"opportunity_summary": msg, "errors": state["errors"] + [msg]}


def _run_outreach_node(state: SupervisorState, outreach_agent) -> dict:
    try:
        learnings = search_gcrm_thoughts("outreach email tone style", limit=5)
        if learnings:
            logger.info("outreach: injecting %d learnings from Open Brain", len(learnings))
        result = outreach_agent.invoke({"limit": 50, "learnings": learnings})
        logger.info("outreach: %s", result.get("summary", ""))
        return {"outreach_summary": result.get("summary", "")}
    except Exception as error:
        msg = f"outreach failed: {error}"
        logger.error(msg)
        return {"outreach_summary": msg, "errors": state["errors"] + [msg]}


def _run_followup_node(state: SupervisorState, followup_agent) -> dict:
    try:
        result = followup_agent.invoke({})
        logger.info("followup: %s", result.get("summary", ""))
        return {"followup_summary": result.get("summary", "")}
    except Exception as error:
        msg = f"followup failed: {error}"
        logger.error(msg)
        return {"followup_summary": msg, "errors": state["errors"] + [msg]}


def _generate_report_node(state: SupervisorState) -> dict:
    cities = sorted({job["city"] for job in state.get("research_jobs", [])})
    lines = [
        f"Supervisor run completed — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Cities researched: {', '.join(cities) if cities else '—'}",
        "",
        "Research:",
    ]
    for summary_line in state.get("research_summaries", []):
        lines.append(f"  {summary_line}")
    lines += [
        "",
        f"Enrich:   {state.get('enrichment_summary', '—')}",
        f"Scout:    {state.get('scout_summary', '—')}",
        f"Opportunity: {state.get('opportunity_summary', '—')}",
        f"Outreach: {state.get('outreach_summary', '—')}",
        f"Followup: {state.get('followup_summary', '—')}",
    ]
    errs = state.get("errors", [])
    if errs:
        lines.append(f"\nErrors ({len(errs)}):")
        for error_msg in errs:
            lines.append(f"  {error_msg}")

    summary = "\n".join(lines)
    status = "failed" if errs and not state.get("scout_summary") else "completed"
    finish_run(state.get("run_id", 0), status, summary[:500], {})
    return {"summary": summary}


def create_supervisor(checkpointer=None):
    """
    Build and compile the supervisor graph with a PostgreSQL checkpointer.
    Node bodies live at module level; the per-agent nodes are bound to their
    concrete agent here. Returns the compiled graph.
    """
    research_agent, enrichment_agent, opportunity_agent, scout_agent, outreach_agent, followup_agent = _build_agents()

    graph = StateGraph(SupervisorState)
    graph.add_node("init", _init_node)
    graph.add_node("run_research", partial(_run_research_node, research_agent=research_agent))
    graph.add_node("run_enrich", partial(_run_enrich_node, enrichment_agent=enrichment_agent))
    graph.add_node("run_opportunity", partial(_run_opportunity_node, opportunity_agent=opportunity_agent))
    graph.add_node("run_scout", partial(_run_scout_node, scout_agent=scout_agent))
    graph.add_node("run_outreach", partial(_run_outreach_node, outreach_agent=outreach_agent))
    graph.add_node("run_followup", partial(_run_followup_node, followup_agent=followup_agent))
    graph.add_node("generate_report", _generate_report_node)

    graph.set_entry_point("init")
    graph.add_edge("init", "run_research")
    graph.add_edge("run_research", "run_enrich")
    graph.add_edge("run_enrich", "run_scout")
    graph.add_edge("run_scout", "run_opportunity")
    graph.add_edge("run_opportunity", "run_outreach")
    graph.add_edge("run_outreach", "run_followup")
    graph.add_edge("run_followup", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile(checkpointer=checkpointer)
