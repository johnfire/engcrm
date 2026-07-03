import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from .protocols import (
    AgentMission, LanguageModel, InboxFetcher, ContactMatcher,
    InteractionLogger, OptOutSetter, BounceHandler, VisitFlagSetter,
    InboxClassificationSaver, OverdueFetcher, ApprovalQueuer,
    WarmOutcomeRecorder, RunStarter, RunFinisher,
)
from .state import FollowupState
from .prompts import (
    classify_reply_prompt, draft_reply_prompt,
    draft_warm_reply_prompt, draft_followup_prompt,
)
from ._utils import parse_json_response

logger = logging.getLogger(__name__)

# Statuses that mean we have already sent outreach to this contact. Replies only
# get classified when the contact is in one of these — a reply from a not-yet-
# contacted contact is noise (or a cold inbound) and is skipped.
POST_OUTREACH_STATUSES = {
    "contacted", "meeting", "networking_visit", "dormant",
    "on_hold", "bad_email", "proposal", "accepted",
}

_BOUNCE_SENDERS = re.compile(
    r"(mailer-daemon|postmaster|delivery.notification|"
    r"mail-daemon|noreply\+bounce|mailerdaemon)",
    re.IGNORECASE,
)
_BOUNCE_SUBJECTS = re.compile(
    r"(undelivered mail|delivery (status notification|failed|failure)|"
    r"returned mail|failure notice|mail delivery failed|"
    r"unzustellbar|zustellungs(fehler|benachrichtigung)|"
    r"nicht zugestellt)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w.\-]+\.[a-z]{2,}", re.IGNORECASE)

# Richer reply taxonomy → interaction outcome stored on the contact.
_OUTCOME_MAP = {
    "interested":     "interested",
    "warm":           "warm",
    "not_interested": "rejected",
    "not_possible":   "not_possible",
    "opt_out":        "no_reply",
    "other":          "no_reply",
}


def _is_bounce(msg: dict) -> bool:
    return bool(
        _BOUNCE_SENDERS.search(msg.get("from_email", ""))
        or _BOUNCE_SUBJECTS.search(msg.get("subject", ""))
    )


def _extract_recipient_emails(msg: dict) -> list[str]:
    """Deduplicated emails from bounce body — one is likely the failed recipient."""
    return list(dict.fromkeys(_EMAIL_RE.findall(msg.get("body", ""))))


def _is_exact_match(contact: dict) -> bool:
    """Whether the contact was matched by exact email rather than a corporate-
    domain fallback. An absent tag means the matcher doesn't distinguish, so we
    treat it as exact and preserve prior behavior."""
    return contact.get("_match_type") != "domain"


def _reply_entry(msg: dict, contact: dict, classification: str, reasoning: str) -> dict:
    """The audit/result record for one classified reply. Per-action helpers
    annotate it further (flags, queued state, error notes)."""
    return {
        "inbox_message_id": msg["id"],
        "contact_id": contact["id"],
        "from_email": msg["from_email"],
        "classification": classification,
        "reasoning": reasoning,
    }


def create_followup_agent(
    llm: LanguageModel,
    fetch_inbox: InboxFetcher,
    match_contact: ContactMatcher,
    log_interaction: InteractionLogger,
    set_opt_out: OptOutSetter,
    handle_bounce: BounceHandler,
    set_visit_when_nearby: VisitFlagSetter,
    save_classification: InboxClassificationSaver,
    fetch_overdue: OverdueFetcher,
    queue_for_approval: ApprovalQueuer,
    record_warm_outcome: WarmOutcomeRecorder,
    start_run: RunStarter,
    finish_run: RunFinisher,
    mission: AgentMission,
    overdue_days: int = 90,
):
    """
    Build and return a compiled LangGraph follow-up agent.

    Processes two work streams per run. Nothing is sent autonomously — every
    drafted email lands in the approval queue for a human to review and send:
      1. Inbox replies — reads unread emails. Delivery-failure bounces are
         detected first and mark the failed contact as bad_email. Remaining
         replies are matched to a known POST-OUTREACH contact (pre-outreach
         and unmatched senders are skipped, not classified), classified by the
         LLM, logged, and acted on:
           - opt_out          → flag opt-out
           - warm             → flag visit_when_nearby + queue a gentle reply draft
           - interested       → queue an enthusiastic reply draft
         Every message gets its classification + reasoning persisted to the
         inbox_messages audit trail.
      2. Overdue contacts — finds contacted contacts with no reply after
         `overdue_days` days and queues a brief nudge for approval.

    Usage:
        agent = create_followup_agent(llm=..., ...)
        result = agent.invoke({})
        print(result["summary"])
    """

    def init(state: FollowupState) -> dict:
        run_id = start_run("followup_agent", {})
        return {
            "run_id": run_id,
            "inbox_messages": [],
            "classified_replies": [],
            "overdue_contacts": [],
            "errors": [],
            "queued_count": 0,
            "opt_out_count": 0,
            "warm_count": 0,
            "bounce_count": 0,
            "summary": "",
        }

    def fetch_inbox_messages(state: FollowupState) -> dict:
        try:
            messages = fetch_inbox()
        except Exception as error:
            return {"errors": state["errors"] + [f"fetch_inbox: {error}"]}
        return {"inbox_messages": messages}

    def _handle_bounce_message(msg: dict) -> int:
        """Process a bounce notification. Returns 1 if a contact was marked bad_email, else 0."""
        bounced_contact = None
        for email in _extract_recipient_emails(msg):
            try:
                c = match_contact(email)
                # Only an exact-email match may be auto-marked bad_email — a
                # domain-only match could be a colleague, not the failed recipient.
                if c and c.get("status") in POST_OUTREACH_STATUSES and _is_exact_match(c):
                    bounced_contact = c
                    break
            except Exception:
                pass

        if bounced_contact:
            try:
                handle_bounce(bounced_contact["id"])
            except Exception as error:
                logger.warning("handle_bounce failed: contact_id=%s error=%s", bounced_contact.get("id"), error)
            try:
                save_classification(
                    msg["id"], bounced_contact["id"], "bounce",
                    f"Delivery failure for {bounced_contact.get('email', '')}",
                )
            except Exception:
                pass
            return 1

        try:
            save_classification(msg["id"], None, "bounce", "No matching contact found in bounce body")
        except Exception:
            pass
        return 0

    def _match_post_outreach_contact(msg: dict):
        """Match a reply to a known post-outreach contact. Records a 'skipped'
        classification and returns None for unmatched or pre-outreach senders —
        replies from those are noise and not worth an LLM classification."""
        contact = None
        try:
            contact = match_contact(msg["from_email"])
        except Exception:
            pass

        if contact is None:
            try:
                save_classification(msg["id"], None, "skipped", "no matching contact")
            except Exception:
                pass
            return None

        if contact.get("status") not in POST_OUTREACH_STATUSES:
            try:
                save_classification(
                    msg["id"], contact["id"], "skipped",
                    f"contact status '{contact.get('status')}' is pre-outreach",
                )
            except Exception:
                pass
            return None

        return contact

    def _classify_reply(msg: dict) -> tuple[str, str]:
        """Run the LLM reply classifier. Returns (classification, reasoning);
        falls back to ('other', error message) on any failure."""
        system, user = classify_reply_prompt(mission, msg)
        try:
            response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            result = parse_json_response(response.content)
            return result.get("classification", "other"), result.get("reasoning", "")
        except Exception as error:
            return "other", f"classification error: {error}"

    def _apply_auto_actions(contact: dict, classification: str, entry: dict) -> tuple[int, int]:
        """Apply immediate opt-out / visit-when-nearby flags — exact-email matches
        only; a domain-only match may be a colleague and is left for human review.
        Returns (opt_out_delta, warm_delta) and annotates entry."""
        opt_out_delta = 0
        warm_delta = 0

        if classification == "opt_out":
            if _is_exact_match(contact):
                try:
                    set_opt_out(contact["id"])
                    opt_out_delta = 1
                except Exception as error:
                    entry["error"] = f"set_opt_out: {error}"
            else:
                entry["auto_action_skipped"] = "opt_out: domain-only match, needs human review"

        if classification == "warm":
            if _is_exact_match(contact):
                try:
                    set_visit_when_nearby(contact["id"])
                    warm_delta = 1
                    entry["visit_flagged"] = True
                except Exception as error:
                    entry["error"] = f"set_visit_when_nearby: {error}"
            else:
                entry["auto_action_skipped"] = "visit_flag: domain-only match, needs human review"

        return opt_out_delta, warm_delta

    def _log_reply_and_signal(contact: dict, classification: str, msg: dict) -> None:
        """Log the inbound interaction; then, only if that committed and the reply
        is warm/interested, record the warm signal for the outreach quality loop."""
        try:
            log_interaction(
                contact_id=contact["id"],
                method="email",
                direction="inbound",
                summary=f"{classification}: {msg.get('subject', '')}",
                outcome=_OUTCOME_MAP.get(classification, "no_reply"),
            )
        except Exception as error:
            logger.warning("log_interaction failed: contact_id=%s error=%s", contact.get("id"), error)
            return

        if classification in ("interested", "warm"):
            try:
                record_warm_outcome(contact["id"])
            except Exception as error:
                logger.warning("record_warm_outcome failed: contact_id=%s error=%s", contact.get("id"), error)

    def _queue_reply_draft(contact: dict, classification: str, msg: dict, run_id: int, entry: dict) -> int:
        """Draft and queue an approval reply for an interested/warm contact —
        interested gets an enthusiastic reply, warm a gentle one. Nothing is sent
        autonomously. Returns 1 if queued, else 0; annotates entry."""
        if not contact.get("email"):
            return 0
        language = contact.get("preferred_language") or mission.language_default
        if classification == "interested":
            sys_p, usr_p = draft_reply_prompt(mission, contact, msg, language)
        else:
            sys_p, usr_p = draft_warm_reply_prompt(mission, contact, msg, language)
        try:
            draft_resp = llm.invoke([SystemMessage(content=sys_p), HumanMessage(content=usr_p)])
            draft = parse_json_response(draft_resp.content)
            queue_for_approval(
                contact_id=contact["id"],
                run_id=run_id,
                subject=draft.get("subject", ""),
                body=draft.get("body", ""),
            )
            entry["reply_queued"] = True
            return 1
        except Exception as error:
            entry["draft_error"] = str(error)
            return 0

    def classify_replies(state: FollowupState) -> dict:
        """Thin orchestrator over the inbox: bounce, match, classify, act, log,
        queue, persist — one step per _-prefixed helper. No behaviour of its own."""
        run_id = state.get("run_id", 0)
        classified = []
        queued = 0
        opt_out_count = 0
        warm_count = 0
        bounce_count = 0

        for msg in state.get("inbox_messages", []):
            # Bounces handled before any LLM classification.
            if _is_bounce(msg):
                bounce_count += _handle_bounce_message(msg)
                continue

            contact = _match_post_outreach_contact(msg)
            if contact is None:
                continue

            classification, reasoning = _classify_reply(msg)
            entry = _reply_entry(msg, contact, classification, reasoning)

            opt_out_delta, warm_delta = _apply_auto_actions(contact, classification, entry)
            opt_out_count += opt_out_delta
            warm_count += warm_delta

            _log_reply_and_signal(contact, classification, msg)

            if classification in ("interested", "warm"):
                queued += _queue_reply_draft(contact, classification, msg, run_id, entry)

            # Persist the classification + reasoning to the inbox audit trail.
            try:
                save_classification(msg["id"], contact["id"], classification, reasoning)
            except Exception:
                pass

            classified.append(entry)

        return {
            "classified_replies": classified,
            "queued_count": queued,
            "opt_out_count": opt_out_count,
            "warm_count": warm_count,
            "bounce_count": bounce_count,
        }

    def fetch_overdue_contacts(state: FollowupState) -> dict:
        try:
            overdue = fetch_overdue(days=overdue_days)
        except Exception as error:
            return {"errors": state["errors"] + [f"fetch_overdue: {error}"], "overdue_contacts": []}
        return {"overdue_contacts": overdue}

    def queue_followup_drafts(state: FollowupState) -> dict:
        """
        Draft follow-up nudges for overdue contacts and put them in the
        approval queue — not sent autonomously. You review and approve.
        """
        run_id = state.get("run_id", 0)
        queued = state.get("queued_count", 0)   # running total — reply drafts already counted
        for contact in state.get("overdue_contacts", []):
            if not contact.get("email"):
                continue
            language = contact.get("preferred_language") or mission.language_default
            days_since = contact.get("days_since_contact", overdue_days)
            original_subject = contact.get("last_subject", "")
            system, user = draft_followup_prompt(mission, contact, days_since, language, original_subject)
            try:
                response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
                draft = parse_json_response(response.content)
                queue_for_approval(
                    contact_id=contact["id"],
                    run_id=run_id,
                    subject=draft.get("subject", ""),
                    body=draft.get("body", ""),
                )
                queued += 1
            except Exception as error:
                logger.warning("overdue follow-up draft failed for contact %s: %s", contact.get("id"), error)
        return {"queued_count": queued}

    def generate_report(state: FollowupState) -> dict:
        inbox_count = len(state.get("classified_replies", []))
        overdue_count = len(state.get("overdue_contacts", []))
        queued = state.get("queued_count", 0)
        opt_outs = state.get("opt_out_count", 0)
        warm = state.get("warm_count", 0)
        bounces = state.get("bounce_count", 0)
        errs = state.get("errors", [])

        summary = (
            f"followup_agent: {inbox_count} replies processed, "
            f"{overdue_count} overdue contacts, "
            f"{queued} drafts queued for approval, "
            f"{warm} warm replies flagged for visit, "
            f"{opt_outs} opt-outs recorded, "
            f"{bounces} bounces marked as bad_email"
        )
        if errs:
            summary += f", {len(errs)} error(s)"

        finish_run(
            state.get("run_id", 0),
            "completed",
            summary,
            {
                "inbox_processed": inbox_count,
                "overdue_handled": overdue_count,
                "queued": queued,
                "warm": warm,
                "opt_outs": opt_outs,
                "bounces": bounces,
            },
        )
        return {"summary": summary}

    graph = StateGraph(FollowupState)
    graph.add_node("init", init)
    graph.add_node("fetch_inbox_messages", fetch_inbox_messages)
    graph.add_node("classify_replies", classify_replies)
    graph.add_node("fetch_overdue_contacts", fetch_overdue_contacts)
    graph.add_node("queue_followup_drafts", queue_followup_drafts)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("init")
    graph.add_edge("init", "fetch_inbox_messages")
    graph.add_edge("fetch_inbox_messages", "classify_replies")
    graph.add_edge("classify_replies", "fetch_overdue_contacts")
    graph.add_edge("fetch_overdue_contacts", "queue_followup_drafts")
    graph.add_edge("queue_followup_drafts", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
