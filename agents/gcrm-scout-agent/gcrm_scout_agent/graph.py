import logging
from functools import partial

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from gcrm.vertical import NOT_A_BUYER_TYPES

from ._utils import parse_json_response
from .prompts import score_organization_prompt
from .protocols import (
    AgentMission,
    CandidateFetcher,
    CityContextFetcher,
    LanguageModel,
    OrganizationStateSetter,
    PageFetcher,
    RunFinisher,
    RunStarter,
)
from .state import ScoutState

logger = logging.getLogger(__name__)
# Contacts Chris entered himself (a card he was handed, a business he walked into, a
# pin on his own Maps list) are his call, not the scout's: they go to ready unscored.
# Everything a machine found is judged — LinkedIn employers and scan hits alike.
HUMAN_ENTERED_SOURCES = {
    "card_capture", "claude_field", "document_capture", "manual", "manual_mobile",
    "manual_web", "maps_import",
}

# What the LLM is allowed to answer, and where each answer puts the contact.
# 'unsure' deliberately leaves it a candidate: an unclear verdict is a request
# for a human look, not a decision, and the reasoning goes into the notes.
FIT_VERDICTS = ("fit", "unsure", "no_fit")
STATE_BY_VERDICT = {
    "fit":    ("suspect", "ready"),
    "unsure": ("candidate", "none"),
    "no_fit": ("not_in_pipeline", "dropped"),
}
# The size band the LLM reads off the website. Outside 50-5,000 employees is never a
# fit, whatever else the LLM liked; inside, the 500-2,500 sweet spot scores highest.
SIZE_BANDS = ("under_50", "50_499", "500_2500", "2501_5000", "over_5000", "unknown")
OUT_OF_RANGE_BANDS = {"under_50", "over_5000"}
FIT_SCORE_BY_BAND = {"500_2500": 85, "50_499": 75, "2501_5000": 75, "unknown": 65}
UNSURE_SCORE, NO_FIT_SCORE = 50, 20


def band_for(employees) -> str | None:
    """The size band for a stated head count, or None when no usable number was given."""
    try:
        count = int(employees)
    except (TypeError, ValueError):
        return None
    for band, upper in (("under_50", 49), ("50_499", 499), ("500_2500", 2500), ("2501_5000", 5000)):
        if count <= upper:
            return band
    return "over_5000"


def decide(outcome: str, size_band: str, employees=None) -> tuple[str, int]:
    """Combine the LLM's verdict with the size rule into (verdict, fit score).
    A stated head count wins over the band the LLM picked."""
    band = band_for(employees) or (size_band if size_band in SIZE_BANDS else "unknown")
    if band in OUT_OF_RANGE_BANDS or outcome == "no_fit":
        return "no_fit", NO_FIT_SCORE
    if outcome == "fit":
        return "fit", FIT_SCORE_BY_BAND[band]
    return "unsure", UNSURE_SCORE


def route(organization: dict, skip_scoring: bool) -> str:
    """'promote' unscored, 'drop' as not a buyer, or 'score' with the LLM."""
    if skip_scoring or organization.get("source") in HUMAN_ENTERED_SOURCES:
        return "promote"
    if (organization.get("type") or "").strip().lower() in NOT_A_BUYER_TYPES:
        return "drop"
    return "score"


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


UNSCORED_STATES = {
    "promote": ("suspect", "ready", UNSURE_SCORE, "Auto-promoted: not scored (entered by hand or scoring skipped)."),
    "drop": ("not_in_pipeline", "dropped", NO_FIT_SCORE, "Not a buyer: {type}."),
}


def split_and_promote(
    state: ScoutState, set_organization_state: OrganizationStateSetter, skip_scoring: bool = False
) -> dict:
    counts, to_score = {"promote": 0, "drop": 0}, []
    for organization in state.get("candidates", []):
        decision = route(organization, skip_scoring)
        if decision == "score":
            to_score.append(organization)
            continue
        stage, status, fit_score, note = UNSCORED_STATES[decision]
        try:
            set_organization_state(
                contact_id=organization["id"], pipeline_stage=stage, status=status,
                fit_score=fit_score, notes=note.format(type=organization.get("type")),
            )
            counts[decision] += 1
        except Exception as error:
            logger.warning("unscored %s failed for contact %s: %s", decision, organization.get("id"), error)
    return {"scored_candidates": to_score, "promoted_count": counts["promote"], "no_fit_count": counts["drop"]}


def fetch_scored_websites(
    state: ScoutState,
    fetch_page: PageFetcher,
    get_or_create_dossier=None,
) -> dict:
    enriched = []
    for candidate in state.get("scored_candidates", []):
        organization, content = dict(candidate), ""
        if organization.get("website"):
            try:
                content = fetch_page(organization["website"])[:4000]
            except Exception:
                pass
        organization["website_content"] = content
        # Enrich with research dossier when available (feature-flagged).
        if get_or_create_dossier and organization.get("website"):
            try:
                dossier = get_or_create_dossier(organization["id"])
                if dossier:
                    organization["dossier"] = dossier
                    logger.debug("scout: dossier available for contact %s", organization["id"])
            except Exception as exc:
                logger.debug("scout: dossier fetch skipped for %s: %s", organization["id"], exc)
        enriched.append(organization)
    return {"scored_candidates": enriched}


def score_candidates(
    state: ScoutState,
    llm: LanguageModel,
    fetch_city_context: CityContextFetcher,
    mission: AgentMission,
) -> dict:
    contexts, scores = {}, []
    for organization in state.get("scored_candidates", []):
        scores.append(_score_organization(organization, contexts, llm, fetch_city_context, mission))
    return {"scores": scores}


def _score_organization(organization, contexts, llm, fetch_city_context, mission) -> dict:
    city, country = organization.get("city", ""), organization.get("country", "DE")
    key = f"{city}:{country}"
    if key not in contexts:
        try:
            contexts[key] = fetch_city_context(city, country)
        except Exception:
            contexts[key] = {}
    try:
        system, user = score_organization_prompt(mission, organization, contexts[key])
        result = parse_json_response(
            llm.invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=user),
                ]
            ).content
        )
        outcome = result.get("outcome", "unsure")
        size_band, employees = str(result.get("size_band", "unknown")), result.get("employees")
        verdict, fit_score = decide(outcome if outcome in FIT_VERDICTS else "unsure", size_band, employees)
        return {
            "contact_id": organization["id"],
            "outcome": verdict,
            "fit_score": fit_score,
            "reasoning": f"Size: {employees or size_band}. {result.get('reasoning', '')}",
        }
    except Exception as error:
        return {
            "contact_id": organization["id"],
            "outcome": "unsure",
            "fit_score": UNSURE_SCORE,
            "reasoning": f"Scoring error — flagged for manual review: {error}",
        }


def apply_scores(state: ScoutState, set_organization_state: OrganizationStateSetter) -> dict:
    counts = {"fit": state.get("promoted_count", 0), "unsure": 0, "no_fit": state.get("no_fit_count", 0)}
    for score in state.get("scores", []):
        verdict = score["outcome"]
        stage, status = STATE_BY_VERDICT[verdict]
        try:
            set_organization_state(
                contact_id=score["contact_id"],
                pipeline_stage=stage,
                status=status,
                fit_score=score["fit_score"],
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
    set_organization_state: OrganizationStateSetter,
    fetch_page: PageFetcher,
    fetch_city_context: CityContextFetcher,
    start_run: RunStarter,
    finish_run: RunFinisher,
    mission: AgentMission,
    get_or_create_dossier=None,
    skip_scoring: bool = False,
):
    """Build a scout graph from small dependency-injected node functions."""
    graph = StateGraph(ScoutState)
    graph.add_node("init", partial(initialize, start_run=start_run))
    graph.add_node("fetch", partial(fetch, fetch_candidates=fetch_candidates))
    graph.add_node(
        "split_and_promote", partial(split_and_promote, set_organization_state=set_organization_state, skip_scoring=skip_scoring)
    )
    graph.add_node(
        "fetch_scored_websites",
        partial(fetch_scored_websites, fetch_page=fetch_page, get_or_create_dossier=get_or_create_dossier),
    )
    graph.add_node(
        "score_candidates",
        partial(score_candidates, llm=llm, fetch_city_context=fetch_city_context, mission=mission),
    )
    graph.add_node("apply_scores", partial(apply_scores, set_organization_state=set_organization_state))
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
