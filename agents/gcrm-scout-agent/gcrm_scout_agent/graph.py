import logging
from functools import partial

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from gcrm.vertical import SCORED_TYPES

from ._utils import parse_json_response
from .prompts import score_contact_prompt
from .protocols import (
    AgentMission,
    CandidateFetcher,
    CityContextFetcher,
    ContactStateSetter,
    LanguageModel,
    PageFetcher,
    RunFinisher,
    RunStarter,
)
from .state import ScoutState

logger = logging.getLogger(__name__)
SCORED_TYPES_LC = {contact_type.lower() for contact_type in SCORED_TYPES}

# What the LLM is allowed to answer, and where each answer puts the contact.
# 'unsure' deliberately leaves it a candidate: an unclear verdict is a request
# for a human look, not a decision, and the reasoning goes into the notes.
FIT_VERDICTS = ("fit", "unsure", "no_fit")
STATE_BY_VERDICT = {
    "fit":    ("suspect", "ready"),
    "unsure": ("candidate", "none"),
    "no_fit": ("not_in_pipeline", "dropped"),
}
FIT_SCORES = {"fit": 75, "unsure": 50, "no_fit": 20}


def initialize(state: ScoutState, start_run: RunStarter) -> dict:
    limit = state.get("limit", 50)
    return {
        "run_id": start_run("scout_agent", {"limit": limit}),
        "limit": limit,
        "candidates": [],
        "scored_candidates": [],
        "scores": [],
        "errors": [],
        "promoted_count": 0,
        "unsure_count": 0,
        "no_fit_count": 0,
        "summary": "",
    }


def fetch(state: ScoutState, fetch_candidates: CandidateFetcher) -> dict:
    try:
        return {"candidates": fetch_candidates(limit=state["limit"])}
    except Exception as error:
        return {"errors": state["errors"] + [f"fetch_candidates: {error}"], "candidates": []}


def split_and_promote(state: ScoutState, set_contact_state: ContactStateSetter) -> dict:
    promoted, to_score = 0, []
    for contact in state.get("candidates", []):
        if (contact.get("type") or "").lower() in SCORED_TYPES_LC:
            to_score.append(contact)
            continue
        try:
            set_contact_state(
                contact_id=contact["id"],
                pipeline_stage="suspect",
                status="ready",
                fit_score=50,
                notes="Auto-promoted: type does not require scoring.",
            )
            promoted += 1
        except Exception as error:
            logger.warning("auto-promote failed for contact %s: %s", contact.get("id"), error)
    return {"scored_candidates": to_score, "promoted_count": promoted}


def fetch_scored_websites(
    state: ScoutState,
    fetch_page: PageFetcher,
    get_or_create_dossier=None,
) -> dict:
    enriched = []
    for candidate in state.get("scored_candidates", []):
        contact, content = dict(candidate), ""
        if contact.get("website"):
            try:
                content = fetch_page(contact["website"])[:4000]
            except Exception:
                pass
        contact["website_content"] = content
        # Enrich with research dossier when available (feature-flagged).
        if get_or_create_dossier and contact.get("website"):
            try:
                dossier = get_or_create_dossier(contact["id"])
                if dossier:
                    contact["dossier"] = dossier
                    logger.debug("scout: dossier available for contact %s", contact["id"])
            except Exception as exc:
                logger.debug("scout: dossier fetch skipped for %s: %s", contact["id"], exc)
        enriched.append(contact)
    return {"scored_candidates": enriched}


def score_candidates(
    state: ScoutState,
    llm: LanguageModel,
    fetch_city_context: CityContextFetcher,
    mission: AgentMission,
) -> dict:
    contexts, scores = {}, []
    for contact in state.get("scored_candidates", []):
        scores.append(_score_contact(contact, contexts, llm, fetch_city_context, mission))
    return {"scores": scores}


def _score_contact(contact, contexts, llm, fetch_city_context, mission) -> dict:
    city, country = contact.get("city", ""), contact.get("country", "DE")
    key = f"{city}:{country}"
    if key not in contexts:
        try:
            contexts[key] = fetch_city_context(city, country)
        except Exception:
            contexts[key] = {}
    try:
        system, user = score_contact_prompt(mission, contact, contexts[key])
        result = parse_json_response(
            llm.invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=user),
                ]
            ).content
        )
        outcome = result.get("outcome", "unsure")
        return {
            "contact_id": contact["id"],
            "outcome": outcome if outcome in FIT_VERDICTS else "unsure",
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as error:
        return {
            "contact_id": contact["id"],
            "outcome": "unsure",
            "reasoning": f"Scoring error — flagged for manual review: {error}",
        }


def apply_scores(state: ScoutState, set_contact_state: ContactStateSetter) -> dict:
    counts = {"fit": state.get("promoted_count", 0), "unsure": 0, "no_fit": 0}
    for score in state.get("scores", []):
        verdict = score["outcome"]
        stage, status = STATE_BY_VERDICT[verdict]
        try:
            set_contact_state(
                contact_id=score["contact_id"],
                pipeline_stage=stage,
                status=status,
                fit_score=FIT_SCORES[verdict],
                notes=score["reasoning"],
            )
            counts[verdict] += 1
        except Exception as error:
            logger.warning("applying score outcome failed: %s", error)
    return {
        "promoted_count": counts["fit"],
        "unsure_count": counts["unsure"],
        "no_fit_count": counts["no_fit"],
    }


def generate_report(state: ScoutState, finish_run: RunFinisher) -> dict:
    promoted, unsure, no_fit = (
        state.get(key, 0) for key in ("promoted_count", "unsure_count", "no_fit_count")
    )
    total, evaluated, errors = (
        len(state.get("candidates", [])),
        len(state.get("scored_candidates", [])),
        state.get("errors", []),
    )
    summary = (
        f"scout_agent: {total} candidates — {promoted} promoted to suspect/ready, "
        f"{unsure} left as candidates for review, {no_fit} taken out of the pipeline "
        f"({evaluated} evaluated by LLM)"
    )
    if errors:
        summary += f", {len(errors)} error(s)"
    finish_run(
        state.get("run_id", 0),
        "completed",
        summary,
        {"promoted": promoted, "unsure": unsure, "no_fit": no_fit, "total": total},
    )
    return {"summary": summary}


def create_scout_agent(
    llm: LanguageModel,
    fetch_candidates: CandidateFetcher,
    set_contact_state: ContactStateSetter,
    fetch_page: PageFetcher,
    fetch_city_context: CityContextFetcher,
    start_run: RunStarter,
    finish_run: RunFinisher,
    mission: AgentMission,
    get_or_create_dossier=None,
):
    """Build a scout graph from small dependency-injected node functions."""
    graph = StateGraph(ScoutState)
    graph.add_node("init", partial(initialize, start_run=start_run))
    graph.add_node("fetch", partial(fetch, fetch_candidates=fetch_candidates))
    graph.add_node(
        "split_and_promote", partial(split_and_promote, set_contact_state=set_contact_state)
    )
    graph.add_node(
        "fetch_scored_websites",
        partial(fetch_scored_websites, fetch_page=fetch_page, get_or_create_dossier=get_or_create_dossier),
    )
    graph.add_node(
        "score_candidates",
        partial(score_candidates, llm=llm, fetch_city_context=fetch_city_context, mission=mission),
    )
    graph.add_node("apply_scores", partial(apply_scores, set_contact_state=set_contact_state))
    graph.add_node("generate_report", partial(generate_report, finish_run=finish_run))
    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "split_and_promote")
    graph.add_edge("split_and_promote", "fetch_scored_websites")
    graph.add_edge("fetch_scored_websites", "score_candidates")
    graph.add_edge("score_candidates", "apply_scores")
    graph.add_edge("apply_scores", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()
