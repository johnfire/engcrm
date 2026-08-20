import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ._utils import parse_json_response
from .prompts import (
    classify_reply_prompt,
    draft_followup_prompt,
    draft_reply_prompt,
    draft_warm_reply_prompt,
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




def init(state: FollowupState, dependencies) -> dict:
    run_id = dependencies.start_run('followup_agent', {})
    return {'run_id': run_id, 'inbox_messages': [], 'classified_replies': [], 'overdue_contacts': [], 'errors': [], 'queued_count': 0, 'opt_out_count': 0, 'warm_count': 0, 'bounce_count': 0, 'summary': ''}

def fetch_inbox_messages(state: FollowupState, dependencies) -> dict:
    try:
        messages = dependencies.fetch_inbox()
    except Exception as error:
        return {'errors': state['errors'] + [f'fetch_inbox: {error}']}
    return {'inbox_messages': messages}

def _handle_bounce_message(msg: dict, dependencies) -> int:
    """Process a bounce notification. Returns 1 if a contact was marked bad_email, else 0."""
    bounced_organization = None
    for email in _extract_recipient_emails(msg):
        try:
            c = dependencies.match_organization(email)
            if c and c.get('status') in POST_OUTREACH_STATUSES and _is_exact_match(c):
                bounced_organization = c
                break
        except Exception:
            pass
    if bounced_organization:
        try:
            dependencies.handle_bounce(bounced_organization['id'])
        except Exception as error:
            logger.warning('handle_bounce failed: contact_id=%s error=%s', bounced_organization.get('id'), error)
        try:
            dependencies.save_classification(msg['id'], bounced_organization['id'], 'bounce', f"Delivery failure for {bounced_organization.get('email', '')}")
        except Exception:
            pass
        return 1
    try:
        dependencies.save_classification(msg['id'], None, 'bounce', 'No matching contact found in bounce body')
    except Exception:
        pass
    return 0

def _match_post_outreach_organization(msg: dict, dependencies):
    """Match a reply to a known post-outreach contact. Records a 'skipped'
        classification and returns None for unmatched or pre-outreach senders —
        replies from those are noise and not worth an LLM classification."""
    organization = None
    try:
        organization = dependencies.match_organization(msg['from_email'])
    except Exception:
        pass
    if organization is None:
        try:
            dependencies.save_classification(msg['id'], None, 'skipped', 'no matching contact')
        except Exception:
            pass
        return None
    if organization.get('status') not in POST_OUTREACH_STATUSES:
        try:
            dependencies.save_classification(msg['id'], organization['id'], 'skipped', f"contact status '{organization.get('status')}' is pre-outreach")
        except Exception:
            pass
        return None
    return organization

def _classify_reply(msg: dict, dependencies) -> tuple[str, str]:
    """Run the LLM reply classifier. Returns (classification, reasoning);
        falls back to ('other', error message) on any failure."""
    system, user = classify_reply_prompt(dependencies.mission, msg)
    try:
        response = dependencies.llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        result = parse_json_response(response.content)
        return (result.get('classification', 'other'), result.get('reasoning', ''))
    except Exception as error:
        return ('other', f'classification error: {error}')

def _apply_auto_actions(msg: dict, organization: dict, classification: str, entry: dict, dependencies) -> tuple[int, int]:
    """Apply immediate opt-out / visit-when-nearby flags — exact-email matches
        only; a domain-only match may be a colleague and is left for human review.
        Returns (opt_out_delta, warm_delta) and annotates entry."""
    opt_out_delta = 0
    warm_delta = 0
    is_authenticated = bool(msg.get('authenticated'))
    if classification == 'opt_out':
        if _is_exact_match(organization) and is_authenticated:
            try:
                dependencies.set_opt_out(organization['id'])
                opt_out_delta = 1
            except Exception as error:
                entry['error'] = f'set_opt_out: {error}'
        elif not is_authenticated:
            entry['auto_action_skipped'] = 'opt_out: needs human review (unauthenticated sender)'
        else:
            entry['auto_action_skipped'] = 'opt_out: domain-only match, needs human review'
    if classification == 'warm':
        if _is_exact_match(organization) and is_authenticated:
            try:
                dependencies.set_visit_when_nearby(organization['id'])
                warm_delta = 1
                entry['visit_flagged'] = True
            except Exception as error:
                entry['error'] = f'set_visit_when_nearby: {error}'
        elif not is_authenticated:
            entry['auto_action_skipped'] = 'visit_flag: needs human review (unauthenticated sender)'
        else:
            entry['auto_action_skipped'] = 'visit_flag: domain-only match, needs human review'
    return (opt_out_delta, warm_delta)

def _log_reply_and_signal(organization: dict, classification: str, msg: dict, dependencies) -> None:
    """Log the inbound interaction; then, only if that committed and the reply
        is warm/interested, record the warm signal for the outreach quality loop."""
    try:
        dependencies.log_interaction(contact_id=organization['id'], method='email', direction='inbound', summary=f"{classification}: {msg.get('subject', '')}", outcome=_OUTCOME_MAP.get(classification, 'no_reply'))
    except Exception as error:
        logger.warning('log_interaction failed: contact_id=%s error=%s', organization.get('id'), error)
        return
    if classification in ('interested', 'warm'):
        try:
            dependencies.record_warm_outcome(organization['id'])
        except Exception as error:
            logger.warning('record_warm_outcome failed: contact_id=%s error=%s', organization.get('id'), error)

def _queue_reply_draft(organization: dict, classification: str, msg: dict, run_id: int, entry: dict, dependencies) -> int:
    """Draft and queue an approval reply for an interested/warm contact —
        interested gets an enthusiastic reply, warm a gentle one. Nothing is sent
        autonomously. Returns 1 if queued, else 0; annotates entry."""
    if not organization.get('email'):
        return 0
    language = organization.get('preferred_language') or dependencies.mission.language_default
    if classification == 'interested':
        sys_p, usr_p = draft_reply_prompt(dependencies.mission, organization, msg, language)
    else:
        sys_p, usr_p = draft_warm_reply_prompt(dependencies.mission, organization, msg, language)
    try:
        draft_resp = dependencies.llm.invoke([SystemMessage(content=sys_p), HumanMessage(content=usr_p)])
        draft = parse_json_response(draft_resp.content)
        dependencies.queue_for_approval(contact_id=organization['id'], run_id=run_id, subject=draft.get('subject', ''), body=draft.get('body', ''))
        entry['reply_queued'] = True
        return 1
    except Exception as error:
        entry['draft_error'] = str(error)
        return 0

def classify_replies(state: FollowupState, dependencies) -> dict:
    """Thin orchestrator over the inbox: bounce, match, classify, act, log,
        queue, persist — one step per _-prefixed helper. No behaviour of its own."""
    run_id = state.get('run_id', 0)
    classified = []
    queued = 0
    opt_out_count = 0
    warm_count = 0
    bounce_count = 0
    for msg in state.get('inbox_messages', []):
        if _is_bounce(msg):
            bounce_count += _handle_bounce_message(msg, dependencies=dependencies)
            continue
        organization = _match_post_outreach_organization(msg, dependencies=dependencies)
        if organization is None:
            continue
        classification, reasoning = _classify_reply(msg, dependencies=dependencies)
        entry = _reply_entry(msg, organization, classification, reasoning)
        opt_out_delta, warm_delta = _apply_auto_actions(msg, organization, classification, entry, dependencies=dependencies)
        opt_out_count += opt_out_delta
        warm_count += warm_delta
        _log_reply_and_signal(organization, classification, msg, dependencies=dependencies)
        if classification in ('interested', 'warm'):
            queued += _queue_reply_draft(organization, classification, msg, run_id, entry, dependencies=dependencies)
        try:
            dependencies.save_classification(msg['id'], organization['id'], classification, reasoning)
        except Exception:
            pass
        classified.append(entry)
    return {'classified_replies': classified, 'queued_count': queued, 'opt_out_count': opt_out_count, 'warm_count': warm_count, 'bounce_count': bounce_count}

def fetch_overdue_contacts(state: FollowupState, dependencies) -> dict:
    try:
        overdue = dependencies.fetch_overdue(days=dependencies.overdue_days)
    except Exception as error:
        return {'errors': state['errors'] + [f'fetch_overdue: {error}'], 'overdue_contacts': []}
    return {'overdue_contacts': overdue}

def queue_followup_drafts(state: FollowupState, dependencies) -> dict:
    """
        Draft follow-up nudges for overdue contacts and put them in the
        approval queue — not sent autonomously. You review and approve.
        """
    run_id = state.get('run_id', 0)
    queued = state.get('queued_count', 0)
    for organization in state.get('overdue_contacts', []):
        if not organization.get('email'):
            continue
        language = organization.get('preferred_language') or dependencies.mission.language_default
        days_since = organization.get('days_since_contact', dependencies.overdue_days)
        original_subject = organization.get('last_subject', '')
        system, user = draft_followup_prompt(dependencies.mission, organization, days_since, language, original_subject)
        try:
            response = dependencies.llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            draft = parse_json_response(response.content)
            dependencies.queue_for_approval(contact_id=organization['id'], run_id=run_id, subject=draft.get('subject', ''), body=draft.get('body', ''))
            queued += 1
        except Exception as error:
            logger.warning('overdue follow-up draft failed for contact %s: %s', organization.get('id'), error)
    return {'queued_count': queued}

def generate_report(state: FollowupState, dependencies) -> dict:
    inbox_count = len(state.get('classified_replies', []))
    overdue_count = len(state.get('overdue_contacts', []))
    queued = state.get('queued_count', 0)
    opt_outs = state.get('opt_out_count', 0)
    warm = state.get('warm_count', 0)
    bounces = state.get('bounce_count', 0)
    errs = state.get('errors', [])
    summary = f'followup_agent: {inbox_count} replies processed, {overdue_count} overdue contacts, {queued} drafts queued for approval, {warm} warm replies flagged for visit, {opt_outs} opt-outs recorded, {bounces} bounces marked as bad_email'
    if errs:
        summary += f', {len(errs)} error(s)'
    dependencies.finish_run(state.get('run_id', 0), 'completed', summary, {'inbox_processed': inbox_count, 'overdue_handled': overdue_count, 'queued': queued, 'warm': warm, 'opt_outs': opt_outs, 'bounces': bounces})
    return {'summary': summary}
