from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from .protocols import AgentMission, LanguageModel, CandidateFetcher, ContactUpdater, PageFetcher, CityContextFetcher, RunStarter, RunFinisher
from .state import ScoutState
from .prompts import score_contact_prompt
from ._utils import parse_json_response

from gcrm.vertical import SCORED_TYPES


def create_scout_agent(
    llm: LanguageModel,
    fetch_candidates: CandidateFetcher,
    update_contact: ContactUpdater,
    fetch_page: PageFetcher,
    fetch_city_context: CityContextFetcher,
    start_run: RunStarter,
    finish_run: RunFinisher,
    mission: AgentMission,
):
    """
    Build and return a compiled LangGraph scout agent.

    Non-gallery contacts (cafes, hotels, restaurants, coworking, etc.) are
    promoted to 'cold' automatically — no LLM evaluation needed.

    Gallery contacts are researched properly: the agent fetches their website,
    reads the full content, and asks the LLM whether they show emerging or
    regional artists. Outcome is cold / maybe / dropped.

    Usage:
        agent = create_scout_agent(llm=..., fetch_candidates=..., ...)
        result = agent.invoke({"limit": 50})
        print(result["summary"])
    """

    def init(state: ScoutState) -> dict:
        run_id = start_run("scout_agent", {"limit": state.get("limit", 50)})
        return {
            "run_id": run_id,
            "limit": state.get("limit", 50),
            "candidates": [],
            "gallery_candidates": [],
            "scores": [],
            "errors": [],
            "promoted_count": 0,
            "maybe_count": 0,
            "dropped_count": 0,
            "summary": "",
        }

    def fetch(state: ScoutState) -> dict:
        try:
            candidates = fetch_candidates(limit=state["limit"])
        except Exception as e:
            return {"errors": state["errors"] + [f"fetch_candidates: {e}"], "candidates": []}
        return {"candidates": candidates}

    def split_and_promote(state: ScoutState) -> dict:
        """
        Non-galleries go straight to cold — no evaluation needed.
        Galleries are collected for website research and LLM scoring.
        """
        promoted = 0
        galleries = []
        for contact in state.get("candidates", []):
            contact_type = (contact.get("type") or "").lower()
            if contact_type in SCORED_TYPES:
                galleries.append(contact)
            else:
                try:
                    update_contact(
                        contact_id=contact["id"],
                        status="cold",
                        fit_score=50,
                        notes="Auto-promoted: non-gallery venue.",
                    )
                    promoted += 1
                except Exception:
                    pass
        return {"gallery_candidates": galleries, "promoted_count": promoted}

    def fetch_gallery_websites(state: ScoutState) -> dict:
        """
        Fetch website content for each gallery candidate.
        Tries the main website; appends fetched text as 'website_content'.
        Galleries with no website still proceed — LLM uses notes to judge.
        """
        enriched = []
        for contact in state.get("gallery_candidates", []):
            contact = dict(contact)
            website = contact.get("website", "")
            website_content = ""
            if website:
                try:
                    website_content = fetch_page(website)
                    # cap at 4000 chars — enough for the LLM to read the page properly
                    website_content = website_content[:4000]
                except Exception:
                    pass
            contact["website_content"] = website_content
            enriched.append(contact)
        return {"gallery_candidates": enriched}

    def score_galleries(state: ScoutState) -> dict:
        """LLM evaluates each gallery based on website content, notes, and city market context."""
        if not state.get("gallery_candidates"):
            return {"scores": []}
        scores = []
        city_context_cache: dict[str, dict] = {}
        for contact in state["gallery_candidates"]:
            city = contact.get("city", "")
            country = contact.get("country", "DE")
            cache_key = f"{city}:{country}"
            if cache_key not in city_context_cache:
                try:
                    city_context_cache[cache_key] = fetch_city_context(city, country)
                except Exception:
                    city_context_cache[cache_key] = {}
            city_context = city_context_cache[cache_key]
            system, user = score_contact_prompt(mission, contact, city_context)
            try:
                response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
                result = parse_json_response(response.content)
                outcome = result.get("outcome", "maybe")
                if outcome not in ("cold", "maybe", "dropped"):
                    outcome = "maybe"
                scores.append({
                    "contact_id": contact["id"],
                    "outcome": outcome,
                    "reasoning": result.get("reasoning", ""),
                })
            except Exception as e:
                scores.append({
                    "contact_id": contact["id"],
                    "outcome": "maybe",
                    "reasoning": f"Scoring error — flagged for manual review: {e}",
                })
        return {"scores": scores}

    def apply_scores(state: ScoutState) -> dict:
        """Write gallery outcomes to the database."""
        maybe = 0
        dropped = 0
        # promoted_count already includes auto-promoted non-galleries
        promoted = state.get("promoted_count", 0)

        outcome_score = {"cold": 75, "maybe": 50, "dropped": 20}

        for s in state.get("scores", []):
            try:
                update_contact(
                    contact_id=s["contact_id"],
                    status=s["outcome"],
                    fit_score=outcome_score.get(s["outcome"], 50),
                    notes=s["reasoning"],
                )
                if s["outcome"] == "cold":
                    promoted += 1
                elif s["outcome"] == "maybe":
                    maybe += 1
                else:
                    dropped += 1
            except Exception:
                pass
        return {"promoted_count": promoted, "maybe_count": maybe, "dropped_count": dropped}

    def generate_report(state: ScoutState) -> dict:
        promoted = state.get("promoted_count", 0)
        maybe = state.get("maybe_count", 0)
        dropped = state.get("dropped_count", 0)
        total = len(state.get("candidates", []))
        gallery_count = len(state.get("gallery_candidates", []))
        errs = state.get("errors", [])

        summary = (
            f"scout_agent: {total} candidates — "
            f"{promoted} promoted to cold, {maybe} flagged maybe, {dropped} dropped "
            f"({gallery_count} galleries evaluated by LLM)"
        )
        if errs:
            summary += f", {len(errs)} error(s)"

        finish_run(
            state.get("run_id", 0),
            "completed",
            summary,
            {"promoted": promoted, "maybe": maybe, "dropped": dropped, "total": total},
        )
        return {"summary": summary}

    graph = StateGraph(ScoutState)
    graph.add_node("init", init)
    graph.add_node("fetch", fetch)
    graph.add_node("split_and_promote", split_and_promote)
    graph.add_node("fetch_gallery_websites", fetch_gallery_websites)
    graph.add_node("score_galleries", score_galleries)
    graph.add_node("apply_scores", apply_scores)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "split_and_promote")
    graph.add_edge("split_and_promote", "fetch_gallery_websites")
    graph.add_edge("fetch_gallery_websites", "score_galleries")
    graph.add_edge("score_galleries", "apply_scores")
    graph.add_edge("apply_scores", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
