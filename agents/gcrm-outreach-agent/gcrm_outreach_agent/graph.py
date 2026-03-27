from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from .protocols import (
    AgentMission, LanguageModel, ReadyContactFetcher, InteractionFetcher,
    ComplianceChecker, ApprovalQueuer, PageFetcher, RunStarter, RunFinisher,
)
from .state import OutreachState
from .prompts import draft_email_prompt
from ._utils import parse_json_response


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
    """
    Build and return a compiled LangGraph outreach agent.

    The agent fetches contacts with status='cold', checks GDPR compliance for each,
    fetches the venue's website and interaction history, drafts a personalized
    first-contact email using the LLM, and queues it for human approval.
    Nothing is sent until a human approves via the UI.

    Usage:
        agent = create_outreach_agent(llm=..., fetch_ready_contacts=..., ...)
        result = agent.invoke({"limit": 20})
        print(result["summary"])
    """

    def init(state: OutreachState) -> dict:
        run_id = start_run("outreach_agent", {"limit": state.get("limit", 20)})
        return {
            "run_id": run_id,
            "limit": state.get("limit", 20),
            "contacts": [],
            "drafts": [],
            "errors": [],
            "queued_count": 0,
            "blocked_count": 0,
            "summary": "",
        }

    def fetch(state: OutreachState) -> dict:
        try:
            contacts = fetch_ready_contacts(limit=state["limit"])
        except Exception as e:
            return {"errors": state["errors"] + [f"fetch_ready_contacts: {e}"], "contacts": []}
        return {"contacts": contacts}

    def draft_all(state: OutreachState) -> dict:
        if not state.get("contacts"):
            return {"drafts": []}
        drafts = []
        for contact in state["contacts"]:
            contact_id = contact["id"]

            # GDPR compliance check — hard block
            try:
                allowed = check_compliance(contact_id)
            except Exception as e:
                drafts.append({"contact_id": contact_id, "blocked_reason": f"compliance check error: {e}"})
                continue

            if not allowed:
                drafts.append({"contact_id": contact_id, "blocked_reason": "opt-out or erasure flag set"})
                continue

            # Fetch interaction history
            try:
                interactions = fetch_interactions(contact_id)
            except Exception:
                interactions = []

            # Fetch venue website
            website_content = ""
            website = contact.get("website", "")
            if website:
                try:
                    website_content = fetch_page(website)
                except Exception:
                    pass

            # Draft the email
            language = contact.get("preferred_language") or mission.language_default
            system, user = draft_email_prompt(
                mission, contact, language,
                interactions=interactions,
                website_content=website_content,
            )
            try:
                response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
                result = parse_json_response(response.content)
                drafts.append({
                    "contact_id": contact_id,
                    "subject": result.get("subject", ""),
                    "body": result.get("body", ""),
                })
            except Exception as e:
                drafts.append({"contact_id": contact_id, "blocked_reason": f"draft error: {e}"})

        return {"drafts": drafts}

    def queue_drafts(state: OutreachState) -> dict:
        run_id = state.get("run_id", 0)
        queued = 0
        blocked = 0
        for draft in state.get("drafts", []):
            if draft.get("blocked_reason"):
                blocked += 1
                continue
            try:
                queue_for_approval(
                    contact_id=draft["contact_id"],
                    run_id=run_id,
                    subject=draft["subject"],
                    body=draft["body"],
                )
                queued += 1
            except Exception:
                blocked += 1
        return {"queued_count": queued, "blocked_count": blocked}

    def generate_report(state: OutreachState) -> dict:
        queued = state.get("queued_count", 0)
        blocked = state.get("blocked_count", 0)
        total = len(state.get("contacts", []))
        errs = state.get("errors", [])
        summary = (
            f"outreach_agent: processed {total} contacts — "
            f"{queued} queued for approval, {blocked} blocked"
        )
        if errs:
            summary += f", {len(errs)} error(s)"
        finish_run(
            state.get("run_id", 0),
            "completed",
            summary,
            {"queued": queued, "blocked": blocked, "total": total},
        )
        return {"summary": summary}

    graph = StateGraph(OutreachState)
    graph.add_node("init", init)
    graph.add_node("fetch", fetch)
    graph.add_node("draft_all", draft_all)
    graph.add_node("queue_drafts", queue_drafts)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "draft_all")
    graph.add_edge("draft_all", "queue_drafts")
    graph.add_edge("queue_drafts", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
