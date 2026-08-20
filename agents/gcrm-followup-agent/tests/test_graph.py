"""
Tests use dummy implementations of every Protocol — no real LLM, DB, or network.

The follow-up agent never sends email: interested/warm replies and overdue
nudges are all drafted and put in the approval queue for a human to send.
"""
from dataclasses import dataclass

from gcrm_followup_agent import create_followup_agent
from langchain_core.messages import AIMessage


@dataclass(frozen=True)
class DummyMission:
    goal: str = "Find art venues"
    identity: str = "Test Artist"
    targets: str = "galleries, cafes"
    fit_criteria: str = "contemporary art friendly"
    outreach_style: str = "personal"
    language_default: str = "de"
    website: str = "https://example.com"
    context: str = ""


class FakeLLM:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._index = 0

    def invoke(self, messages):
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        return AIMessage(content=response)


SAMPLE_MESSAGE = {
    "id": 1,
    "message_id": "<abc@proton.me>",
    "from_email": "gallery@example.com",
    "subject": "Re: Ausstellungsanfrage",
    "body": "Vielen Dank für Ihre Anfrage. Wir würden uns sehr freuen...",
    "received_at": "2026-03-01T10:00:00",
    "authenticated": True,
}

# A delivery-failure bounce: mailer-daemon sender + German "unzustellbar" subject,
# with the failed recipient address in the body.
BOUNCE_MESSAGE = {
    "id": 2,
    "message_id": "<bounce@mail.example.net>",
    "from_email": "MAILER-DAEMON@mail.example.net",
    "subject": "Unzustellbar: Ausstellungsanfrage",
    "body": (
        "Diese Nachricht wurde automatisch erstellt.\n"
        "Die Zustellung an folgende Empfänger ist fehlgeschlagen:\n"
        "gallery@example.com\n"
    ),
    "received_at": "2026-03-01T10:05:00",
    "content_type": "multipart/report; report-type=delivery-status",
}

# Post-outreach contact: status must be in POST_OUTREACH_STATUSES, otherwise the
# pre-outreach guard skips classification.
SAMPLE_CONTACT = {
    "id": 10,
    "name": "Galerie Nord",
    "city": "Munich",
    "type": "gallery",
    "email": "gallery@example.com",
    "preferred_language": "de",
    "status": "contacted",
}

OVERDUE_CONTACT = {
    "id": 20,
    "name": "Galerie Süd",
    "city": "Augsburg",
    "type": "gallery",
    "email": "sued@example.com",
    "preferred_language": "de",
    "days_since_contact": 95,
    "last_subject": "Ausstellungsanfrage",
    "status": "contacted",
}

DRAFT = '{"subject": "Re: Danke", "body": "Vielen Dank für Ihr Interesse..."}'
FOLLOWUP_DRAFT = '{"subject": "Kurze Nachfrage", "body": "Ich wollte kurz nachfragen..."}'


def make_tools(
    inbox=None,
    organization_for_email=None,
    overdue=None,
):
    opt_outs = []
    interactions = []
    bounced = []
    visit_flagged = []
    classifications = []   # (msg_id, contact_id, classification, reasoning)
    queued = []
    warm = []
    runs = {}

    def fetch_inbox():
        return inbox if inbox is not None else [SAMPLE_MESSAGE]

    def match_organization(from_email):
        return organization_for_email

    def log_interaction(contact_id, method, direction, summary, outcome):
        interactions.append({"contact_id": contact_id, "direction": direction, "outcome": outcome})

    def set_opt_out(contact_id):
        opt_outs.append(contact_id)

    def handle_bounce(contact_id):
        bounced.append(contact_id)

    def set_visit_when_nearby(contact_id):
        visit_flagged.append(contact_id)

    def save_classification(inbox_message_id, contact_id, classification, reasoning):
        classifications.append((inbox_message_id, contact_id, classification, reasoning))

    def fetch_overdue(days=90):
        return overdue if overdue is not None else []

    def queue_for_approval(contact_id, run_id, subject, body):
        queued.append({"contact_id": contact_id, "subject": subject, "body": body})
        return len(queued)

    def record_warm_outcome(contact_id):
        warm.append(contact_id)

    def start_run(agent_name, input_data):
        run_id = len(runs) + 1
        runs[run_id] = {"status": "running"}
        return run_id

    def finish_run(run_id, status, summary, output_data):
        runs[run_id]["status"] = status

    return {
        "fetch_inbox": fetch_inbox,
        "match_organization": match_organization,
        "log_interaction": log_interaction,
        "set_opt_out": set_opt_out,
        "handle_bounce": handle_bounce,
        "set_visit_when_nearby": set_visit_when_nearby,
        "save_classification": save_classification,
        "fetch_overdue": fetch_overdue,
        "queue_for_approval": queue_for_approval,
        "record_warm_outcome": record_warm_outcome,
        "start_run": start_run,
        "finish_run": finish_run,
        # spies
        "opt_outs": opt_outs,
        "interactions": interactions,
        "bounced": bounced,
        "visit_flagged": visit_flagged,
        "classifications": classifications,
        "queued": queued,
        "warm": warm,
        "runs": runs,
    }


def make_agent(llm, **tool_overrides):
    t = make_tools(**tool_overrides)
    agent = create_followup_agent(
        llm=llm,
        fetch_inbox=t["fetch_inbox"],
        match_organization=t["match_organization"],
        log_interaction=t["log_interaction"],
        set_opt_out=t["set_opt_out"],
        handle_bounce=t["handle_bounce"],
        set_visit_when_nearby=t["set_visit_when_nearby"],
        save_classification=t["save_classification"],
        fetch_overdue=t["fetch_overdue"],
        queue_for_approval=t["queue_for_approval"],
        record_warm_outcome=t["record_warm_outcome"],
        start_run=t["start_run"],
        finish_run=t["finish_run"],
        mission=DummyMission(),
    )
    return agent, t


def test_interested_reply_logs_and_queues():
    llm = FakeLLM([
        '{"classification": "interested", "reasoning": "They want to meet"}',
        DRAFT,   # draft_reply response
    ])
    agent, t = make_agent(llm=llm, organization_for_email=SAMPLE_CONTACT)

    result = agent.invoke({})

    # interaction logged as inbound/interested
    assert any(i["direction"] == "inbound" and i["outcome"] == "interested" for i in t["interactions"])
    # reply drafted and queued for approval — never sent autonomously
    assert result["queued_count"] == 1
    assert t["queued"][0]["contact_id"] == 10
    assert t["queued"][0]["subject"] == "Re: Danke"
    # warm-outcome recorded (interested counts as a positive signal)
    assert 10 in t["warm"]
    # no opt-out
    assert t["opt_outs"] == []
    assert result["opt_out_count"] == 0
    # classification persisted to the audit trail
    assert (1, 10, "interested", "They want to meet") in t["classifications"]


def test_warm_reply_flags_visit_and_queues_gentle_reply():
    """A warm reply flags visit_when_nearby and queues a (gentle) reply draft for approval."""
    llm = FakeLLM([
        '{"classification": "warm", "reasoning": "Friendly but no commitment"}',
        DRAFT,   # draft_warm_reply response
    ])
    agent, t = make_agent(llm=llm, organization_for_email=SAMPLE_CONTACT)

    result = agent.invoke({})

    # visit flag set + counted
    assert 10 in t["visit_flagged"]
    assert result["warm_count"] == 1
    # interaction logged with the warm outcome
    assert any(i["outcome"] == "warm" for i in t["interactions"])
    # warm-outcome recorded for the quality loop
    assert 10 in t["warm"]
    # gentle reply drafted and queued for approval
    assert result["queued_count"] == 1
    assert t["queued"][0]["contact_id"] == 10
    # audit trail records the warm classification
    assert (1, 10, "warm", "Friendly but no commitment") in t["classifications"]


def test_opt_out_reply_sets_flag_and_does_not_queue():
    llm = FakeLLM(['{"classification": "opt_out", "reasoning": "Asked to be removed"}'])
    agent, t = make_agent(llm=llm, organization_for_email=SAMPLE_CONTACT)

    result = agent.invoke({})

    assert 10 in t["opt_outs"]
    assert result["opt_out_count"] == 1
    assert result["queued_count"] == 0
    assert t["queued"] == []
    assert t["visit_flagged"] == []


def test_unauthenticated_opt_out_needs_human_review():
    llm = FakeLLM(['{"classification": "opt_out", "reasoning": "Asked to be removed"}'])
    agent, t = make_agent(
        llm=llm,
        inbox=[{**SAMPLE_MESSAGE, "authenticated": False}],
        organization_for_email=SAMPLE_CONTACT,
    )

    result = agent.invoke({})

    assert t["opt_outs"] == []
    assert result["classified_replies"][0]["auto_action_skipped"] == (
        "opt_out: needs human review (unauthenticated sender)"
    )


def test_domain_only_match_does_not_auto_opt_out():
    """A reply that matches a contact only by corporate domain (not exact email)
    must not auto-apply the irreversible opt-out — it's classified and recorded
    for human review instead."""
    llm = FakeLLM(['{"classification": "opt_out", "reasoning": "Asked to be removed"}'])
    domain_organization = {**SAMPLE_CONTACT, "_match_type": "domain"}
    agent, t = make_agent(llm=llm, organization_for_email=domain_organization)

    result = agent.invoke({})

    assert t["opt_outs"] == []
    assert result["opt_out_count"] == 0
    # still classified + recorded in the audit trail
    assert any(c[2] == "opt_out" for c in t["classifications"])


def test_not_interested_reply_logs_and_does_not_queue():
    llm = FakeLLM(['{"classification": "not_interested", "reasoning": "Not interested"}'])
    agent, t = make_agent(llm=llm, organization_for_email=SAMPLE_CONTACT)

    result = agent.invoke({})

    # not_interested maps to the "rejected" interaction outcome
    assert any(i["outcome"] == "rejected" for i in t["interactions"])
    assert result["queued_count"] == 0
    assert t["queued"] == []
    assert t["opt_outs"] == []
    assert t["visit_flagged"] == []


def test_bounce_marks_organization_bad_email_before_classification():
    """A delivery-failure bounce marks the failed contact bad_email and never hits the LLM."""

    def llm_should_not_run(messages):
        raise AssertionError("LLM must not be invoked for a bounce")

    class GuardLLM:
        invoke = staticmethod(llm_should_not_run)

    # Contact resolves for the recipient address pulled from the bounce body.
    agent, t = make_agent(llm=GuardLLM(), inbox=[BOUNCE_MESSAGE], organization_for_email=SAMPLE_CONTACT)

    result = agent.invoke({})

    assert result["bounce_count"] == 1
    assert 10 in t["bounced"]
    # bounce is not a "classified reply", and nothing is queued
    assert result["queued_count"] == 0
    assert t["queued"] == []
    # audit trail records the bounce
    assert any(c[2] == "bounce" for c in t["classifications"])


def test_overdue_contact_gets_followup_queued():
    llm = FakeLLM([
        # No inbox messages so classify_replies makes no LLM calls
        FOLLOWUP_DRAFT,  # draft_followup response
    ])
    agent, t = make_agent(llm=llm, inbox=[], overdue=[OVERDUE_CONTACT])

    result = agent.invoke({})

    # Overdue nudges are queued for human approval.
    assert result["queued_count"] == 1
    assert t["queued"][0]["contact_id"] == 20
    assert t["queued"][0]["subject"] == "Kurze Nachfrage"


def test_empty_inbox_and_no_overdue():
    llm = FakeLLM(["{}"])
    agent, t = make_agent(llm=llm, inbox=[], overdue=[])

    result = agent.invoke({})

    assert result["queued_count"] == 0
    assert result["opt_out_count"] == 0
    assert "0 replies processed" in result["summary"]


def test_unmatched_inbox_message_recorded_and_skipped():
    """Message from unknown sender: recorded as skipped, no LLM, no interaction, nothing queued."""

    def llm_should_not_run(messages):
        raise AssertionError("LLM must not classify an unmatched sender")

    class GuardLLM:
        invoke = staticmethod(llm_should_not_run)

    agent, t = make_agent(llm=GuardLLM(), organization_for_email=None)  # no contact match

    result = agent.invoke({})

    # No interaction logged (no contact to link to)
    assert t["interactions"] == []
    # Nothing queued
    assert result["queued_count"] == 0
    assert t["queued"] == []
    # Recorded in the audit trail as skipped (replaces the old mark_processed call)
    assert (1, None, "skipped", "no matching contact") in t["classifications"]


def test_pre_outreach_organization_reply_is_skipped():
    """A reply from a contact we haven't reached out to yet is skipped, not classified."""

    def llm_should_not_run(messages):
        raise AssertionError("LLM must not classify a pre-outreach contact's reply")

    class GuardLLM:
        invoke = staticmethod(llm_should_not_run)

    pre_outreach = {**SAMPLE_CONTACT, "status": "new"}
    agent, t = make_agent(llm=GuardLLM(), organization_for_email=pre_outreach)

    result = agent.invoke({})

    assert result["queued_count"] == 0
    assert t["interactions"] == []
    # Recorded with a pre-outreach reason
    assert any(c[1] == 10 and c[2] == "skipped" and "pre-outreach" in c[3] for c in t["classifications"])


def test_queue_failure_does_not_crash():
    """Regression guard: a failing queue_for_approval must not crash the run. The
    draft+queue step is wrapped per-message, so one queue failure is isolated and
    the run still completes."""
    llm = FakeLLM([
        '{"classification": "interested", "reasoning": "Interested"}',
        DRAFT,
    ])

    def boom(contact_id, run_id, subject, body):
        raise RuntimeError("queue down")

    agent = create_followup_agent(
        llm=llm,
        fetch_inbox=lambda: [SAMPLE_MESSAGE],
        match_organization=lambda from_email: SAMPLE_CONTACT,
        log_interaction=lambda **kwargs: None,
        set_opt_out=lambda contact_id: None,
        handle_bounce=lambda contact_id: None,
        set_visit_when_nearby=lambda contact_id: None,
        save_classification=lambda inbox_message_id, contact_id, classification, reasoning: None,
        fetch_overdue=lambda days=90: [],
        queue_for_approval=boom,
        record_warm_outcome=lambda contact_id: None,
        start_run=lambda agent_name, input_data: 1,
        finish_run=lambda run_id, status, summary, output_data: None,
        mission=DummyMission(),
    )

    result = agent.invoke({})

    # Attempted but failed — no crash, nothing counted as queued.
    assert result["queued_count"] == 0
    assert "replies processed" in result["summary"]


def test_log_interaction_failure_does_not_crash():
    """Regression guard: a failing log_interaction must not crash the run. The
    agent's exception path calls logger.warning(), so the module must define a
    logger — otherwise it NameErrors and takes down the very error handling that
    is supposed to keep the run alive."""
    llm = FakeLLM(['{"classification": "not_interested", "reasoning": "n/a"}'])

    def boom(**kwargs):
        raise RuntimeError("db down")

    agent = create_followup_agent(
        llm=llm,
        fetch_inbox=lambda: [SAMPLE_MESSAGE],
        match_organization=lambda from_email: SAMPLE_CONTACT,
        log_interaction=boom,
        set_opt_out=lambda contact_id: None,
        handle_bounce=lambda contact_id: None,
        set_visit_when_nearby=lambda contact_id: None,
        save_classification=lambda inbox_message_id, contact_id, classification, reasoning: None,
        fetch_overdue=lambda days=90: [],
        queue_for_approval=lambda **kwargs: 1,
        record_warm_outcome=lambda contact_id: None,
        start_run=lambda agent_name, input_data: 1,
        finish_run=lambda run_id, status, summary, output_data: None,
        mission=DummyMission(),
    )

    result = agent.invoke({})

    # Run still completes despite the logging failure inside classify_replies.
    assert "replies processed" in result["summary"]
