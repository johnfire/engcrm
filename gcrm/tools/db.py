"""
The stable import surface for the database tools injected into the agents.

Most names here forward to the focused modules that own the implementation
(``db_contacts``, ``db_approvals``, ``db_interactions``); only the handful of
functions defined below still live in this module. Every query is
parameterised — no string interpolation on user data.
"""

import logging

from gcrm.db.connection import db, serialize_row
from gcrm.tools import db_approvals, db_contacts, db_interactions
from gcrm.tools.db_agent_runs import finish_run, get_run_costs, start_run
from gcrm.tools.db_cities import (
    add_city,
    build_research_overview,
    can_run_level,
    get_all_city_scan_status,
    get_cities,
    get_city_market_context,
    get_city_scan_status,
    record_scan_result,
    update_city_market,
)
from gcrm.tools.db_inbox import (
    get_unprocessed_inbox,
    mark_bad_email,
    mark_message_processed,
    save_inbox_classification,
    save_inbox_message,
    set_visit_when_nearby,
)
from gcrm.tools.db_outreach import get_outreach_outcomes, record_warm_outcome
from gcrm.tools.db_people import get_people, get_person, save_person
from gcrm.tools.db_users import (
    create_user,
    get_user_by_email,
    get_user_token_version,
    list_users,
    set_user_active,
    set_user_password,
    touch_user_login,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
































# ---------------------------------------------------------------------------
# GDPR / Compliance
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------




def search_contacts_by_name(query: str, limit: int = 5) -> list[dict]:
    """Fuzzy contact search by business name or decision-maker — for voice-memo matching."""
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, city, email, phone, decision_maker FROM contacts "
            "WHERE deleted_at IS NULL AND (name ILIKE %s OR decision_maker ILIKE %s) "
            "ORDER BY (lower(name) = lower(%s)) DESC, name ASC LIMIT %s",
            (like, like, q, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def log_voice_interaction(
    contact_id: int,
    summary: str,
    *,
    outcome: str | None = None,
    next_action: str | None = None,
    next_action_date: str | None = None,
) -> None:
    """Log a voice-memo interaction (method='voice'), with an optional follow-up date."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO interactions "
            "(contact_id, interaction_date, method, direction, summary, outcome, next_action, next_action_date) "
            "VALUES (%s, CURRENT_DATE, 'voice', NULL, %s, %s, %s, %s)",
            (contact_id, summary, outcome, next_action, next_action_date or None),
        )
        cur.execute("UPDATE contacts SET updated_at = NOW() WHERE id = %s", (contact_id,))


def get_overdue_contacts(days: int = 90) -> list[dict]:
    """
    Return contacts with status='contacted' that haven't had an interaction
    in `days` days, or whose next_action_date is in the past.
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                c.*,
                EXTRACT(DAY FROM NOW() - MAX(i.interaction_date))::int AS days_since_contact,
                (
                    SELECT summary FROM interactions
                    WHERE contact_id = c.id
                    ORDER BY interaction_date DESC LIMIT 1
                ) AS last_subject
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            WHERE c.status = 'contacted'
            GROUP BY c.id
            HAVING
                MAX(i.interaction_date) < CURRENT_DATE - INTERVAL '%s days'
                OR MAX(i.interaction_date) IS NULL
            ORDER BY MAX(i.interaction_date) ASC NULLS FIRST
            LIMIT 30
            """,
            (days,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------




# Compatibility exports: callers may retain ``gcrm.tools.db`` while focused
# modules own the implementation.
def _contact_tool(tool_name, *args, **kwargs):
    db_contacts.db = db
    return getattr(db_contacts, tool_name)(*args, **kwargs)


def get_ignored_chains(*args, **kwargs):
    return _contact_tool("get_ignored_chains", *args, **kwargs)


def save_contact(*args, **kwargs):
    return _contact_tool("save_contact", *args, **kwargs)


def get_existing_contact_names(*args, **kwargs):
    return _contact_tool("get_existing_contact_names", *args, **kwargs)


def update_contact_google_data(*args, **kwargs):
    return _contact_tool("update_contact_google_data", *args, **kwargs)


def get_candidates(*args, **kwargs):
    return _contact_tool("get_candidates", *args, **kwargs)


def get_cold_contacts(*args, **kwargs):
    return _contact_tool("get_cold_contacts", *args, **kwargs)


def update_contact(*args, **kwargs):
    return _contact_tool("update_contact", *args, **kwargs)


def get_contacts_needing_enrichment(*args, **kwargs):
    return _contact_tool("get_contacts_needing_enrichment", *args, **kwargs)


def update_contact_details(*args, **kwargs):
    return _contact_tool("update_contact_details", *args, **kwargs)


def match_contact_by_email(*args, **kwargs):
    return _contact_tool("match_contact_by_email", *args, **kwargs)


def get_contact(*args, **kwargs):
    return _contact_tool("get_contact", *args, **kwargs)


def ensure_consent_log(*args, **kwargs):
    db_approvals.db = db
    return db_approvals.ensure_consent_log(*args, **kwargs)


def check_compliance(*args, **kwargs):
    db_approvals.db = db
    return db_approvals.check_compliance(*args, **kwargs)


def set_opt_out(*args, **kwargs):
    db_approvals.db = db
    return db_approvals.set_opt_out(*args, **kwargs)


def queue_for_approval(*args, **kwargs):
    db_approvals.db = db
    return db_approvals.queue_for_approval(*args, **kwargs)


def log_interaction(*args, **kwargs):
    db_interactions.db = db
    return db_interactions.log_interaction(*args, **kwargs)


def get_contact_interactions(*args, **kwargs):
    db_interactions.db = db
    return db_interactions.get_contact_interactions(*args, **kwargs)


__all__ = [
    "add_city",
    "build_research_overview",
    "can_run_level",
    "check_compliance",
    "create_user",
    "ensure_consent_log",
    "finish_run",
    "get_all_city_scan_status",
    "get_candidates",
    "get_cities",
    "get_city_market_context",
    "get_city_scan_status",
    "get_cold_contacts",
    "get_contact_interactions",
    "get_contacts_needing_enrichment",
    "get_existing_contact_names",
    "get_ignored_chains",
    "get_outreach_outcomes",
    "get_overdue_contacts",
    "get_people",
    "get_person",
    "get_run_costs",
    "get_unprocessed_inbox",
    "get_user_by_email",
    "get_user_token_version",
    "list_users",
    "log_interaction",
    "mark_bad_email",
    "mark_message_processed",
    "match_contact_by_email",
    "queue_for_approval",
    "record_scan_result",
    "record_warm_outcome",
    "save_contact",
    "save_inbox_classification",
    "save_inbox_message",
    "save_person",
    "set_opt_out",
    "set_user_active",
    "set_user_password",
    "set_visit_when_nearby",
    "start_run",
    "touch_user_login",
    "update_city_market",
    "update_contact",
    "update_contact_details",
]
