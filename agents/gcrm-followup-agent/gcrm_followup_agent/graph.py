import logging
import re

from langgraph.graph import END, StateGraph

from .protocols import (
    AgentMission,
    ApprovalQueuer,
    BounceHandler,
    InboxClassificationSaver,
    InboxFetcher,
    InteractionLogger,
    LanguageModel,
    OptOutSetter,
    OrganizationMatcher,
    OverdueFetcher,
    RunFinisher,
    RunStarter,
    VisitFlagSetter,
    WarmOutcomeRecorder,
)
from .state import FollowupState

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
    return msg.get("content_type", "").lower().startswith("multipart/report") and bool(
        _BOUNCE_SENDERS.search(msg.get("from_email", ""))
        or _BOUNCE_SUBJECTS.search(msg.get("subject", ""))
    )


def _extract_recipient_emails(msg: dict) -> list[str]:
    """Deduplicated emails from bounce body — one is likely the failed recipient."""
    return list(dict.fromkeys(_EMAIL_RE.findall(msg.get("body", ""))))


def _is_exact_match(organization: dict) -> bool:
    """Whether the contact was matched by exact email rather than a corporate-
    domain fallback. An absent tag means the matcher doesn't distinguish, so we
    treat it as exact and preserve prior behavior."""
    return organization.get("_match_type") != "domain"


def _reply_entry(msg: dict, organization: dict, classification: str, reasoning: str) -> dict:
    """The audit/result record for one classified reply. Per-action helpers
    annotate it further (flags, queued state, error notes)."""
    return {
        "inbox_message_id": msg["id"],
        "contact_id": organization["id"],
        "from_email": msg["from_email"],
        "classification": classification,
        "reasoning": reasoning,
    }


def create_followup_agent(llm: LanguageModel, fetch_inbox: InboxFetcher, match_organization: OrganizationMatcher, log_interaction: InteractionLogger, set_opt_out: OptOutSetter, handle_bounce: BounceHandler, set_visit_when_nearby: VisitFlagSetter, save_classification: InboxClassificationSaver, fetch_overdue: OverdueFetcher, queue_for_approval: ApprovalQueuer, record_warm_outcome: WarmOutcomeRecorder, start_run: RunStarter, finish_run: RunFinisher, mission: AgentMission, overdue_days: int = 90):
    """Build the follow-up graph from module-level dependency-injected nodes."""
    from functools import partial
    from types import SimpleNamespace

    from . import nodes
    dependencies = SimpleNamespace(**locals())
    names = ("init", "fetch_inbox_messages", "classify_replies", "fetch_overdue_contacts", "queue_followup_drafts", "generate_report")
    graph = StateGraph(FollowupState)
    for name in names:
        graph.add_node(name, partial(getattr(nodes, name), dependencies=dependencies))
    graph.set_entry_point("init")
    for source, target in zip(names, names[1:]):
        graph.add_edge(source, target)
    graph.add_edge("generate_report", END)
    return graph.compile()
