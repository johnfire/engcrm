from functools import partial

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from ._utils import parse_json_response
from .prompts import draft_email_prompt
from .protocols import (
    AgentMission,
    ApprovalQueuer,
    ComplianceChecker,
    InteractionFetcher,
    LanguageModel,
    PageFetcher,
    ReadyContactFetcher,
    RunFinisher,
    RunStarter,
)
from .state import OutreachState


def initialize(state: OutreachState, start_run: RunStarter) -> dict:
    limit = state.get("limit", 20)
    return {
        "run_id": start_run("outreach_agent", {"limit": limit}),
        "limit": limit,
        "learnings": state.get("learnings", []),
        "contacts": [],
        "drafts": [],
        "errors": [],
        "queued_count": 0,
        "blocked_count": 0,
        "summary": "",
    }


def fetch_contacts(state: OutreachState, fetch_ready_contacts: ReadyContactFetcher) -> dict:
    try:
        return {"contacts": fetch_ready_contacts(limit=state["limit"])}
    except Exception as error:
        return {"errors": state["errors"] + [f"fetch_ready_contacts: {error}"], "contacts": []}


def draft_contacts(
    state: OutreachState,
    llm: LanguageModel,
    fetch_interactions: InteractionFetcher,
    fetch_page: PageFetcher,
    check_compliance: ComplianceChecker,
    mission: AgentMission,
) -> dict:
    drafts = []
    for contact in state.get("contacts", []):
        drafts.append(
            _draft_contact(
                contact,
                state.get("learnings", []),
                llm,
                fetch_interactions,
                fetch_page,
                check_compliance,
                mission,
            )
        )
    return {"drafts": drafts}


def _draft_contact(
    contact: dict,
    learnings: list[str],
    llm: LanguageModel,
    fetch_interactions: InteractionFetcher,
    fetch_page: PageFetcher,
    check_compliance: ComplianceChecker,
    mission: AgentMission,
) -> dict:
    contact_id = contact["id"]
    try:
        if not check_compliance(contact_id):
            return {"contact_id": contact_id, "blocked_reason": "opt-out or erasure flag set"}
    except Exception as error:
        return {"contact_id": contact_id, "blocked_reason": f"compliance check error: {error}"}
    interactions = _load_interactions(contact_id, fetch_interactions)
    website_content = _load_website(contact, fetch_page)
    system, user = draft_email_prompt(
        mission,
        contact,
        contact.get("preferred_language") or mission.language_default,
        interactions=interactions,
        website_content=website_content,
        learnings=learnings,
    )
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        draft = parse_json_response(response.content)
        return {
            "contact_id": contact_id,
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
        }
    except Exception as error:
        return {"contact_id": contact_id, "blocked_reason": f"draft error: {error}"}


def _load_interactions(contact_id: int, fetch_interactions: InteractionFetcher) -> list[dict]:
    try:
        return fetch_interactions(contact_id)
    except Exception:
        return []


def _load_website(contact: dict, fetch_page: PageFetcher) -> str:
    try:
        return fetch_page(contact["website"]) if contact.get("website") else ""
    except Exception:
        return ""


def queue_drafts(state: OutreachState, queue_for_approval: ApprovalQueuer) -> dict:
    queued = blocked = 0
    for draft in state.get("drafts", []):
        if draft.get("blocked_reason"):
            blocked += 1
            continue
        try:
            queue_for_approval(
                draft["contact_id"],
                state.get("run_id", 0),
                draft["subject"],
                draft["body"],
            )
            queued += 1
        except Exception:
            blocked += 1
    return {"queued_count": queued, "blocked_count": blocked}


def generate_report(state: OutreachState, finish_run: RunFinisher) -> dict:
    queued, blocked = state.get("queued_count", 0), state.get("blocked_count", 0)
    total, errors = len(state.get("contacts", [])), state.get("errors", [])
    summary = f"outreach_agent: processed {total} contacts — {queued} queued for approval, {blocked} blocked"
    if errors:
        summary += f", {len(errors)} error(s)"
    finish_run(
        state.get("run_id", 0),
        "completed",
        summary,
        {"queued": queued, "blocked": blocked, "total": total},
    )
    return {"summary": summary}


def create_outreach_agent(
    llm: LanguageModel,
    fetch_ready_contacts: ReadyContactFetcher,
    fetch_interactions: InteractionFetcher,
    fetch_page: PageFetcher,
    check_compliance: ComplianceChecker,
    queue_for_approval: ApprovalQueuer,
    start_run: RunStarter,
    finish_run: RunFinisher,
    mission: AgentMission,
):
    """Build an outreach graph from small dependency-injected node functions."""
    graph = StateGraph(OutreachState)
    graph.add_node("init", partial(initialize, start_run=start_run))
    graph.add_node("fetch", partial(fetch_contacts, fetch_ready_contacts=fetch_ready_contacts))
    graph.add_node(
        "draft_all",
        partial(
            draft_contacts,
            llm=llm,
            fetch_interactions=fetch_interactions,
            fetch_page=fetch_page,
            check_compliance=check_compliance,
            mission=mission,
        ),
    )
    graph.add_node("queue_drafts", partial(queue_drafts, queue_for_approval=queue_for_approval))
    graph.add_node("generate_report", partial(generate_report, finish_run=finish_run))
    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "draft_all")
    graph.add_edge("draft_all", "queue_drafts")
    graph.add_edge("queue_drafts", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()
