"""
All database operations used as injected tools in the agents.
Every function uses parameterised queries — no string interpolation on user data.
"""
import difflib
import json
import logging
import re
from datetime import date, datetime, timezone

from gcrm.db.connection import db, serialize_row
from gcrm.tools.email_domains import FREEMAIL_DOMAINS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def _load_ignored_chains(cur) -> list[str]:
    cur.execute("SELECT name FROM ignored_chains")
    return [row["name"] for row in cur.fetchall()]


def get_ignored_chains() -> list[str]:
    """Return all chain names from the ignored_chains blocklist."""
    with db() as conn:
        cur = conn.cursor()
        return _load_ignored_chains(cur)


def _normalize_for_chain_match(name: str) -> str:
    return re.sub(r"[\s\-_/&'\".,;:!?]+", " ", name.lower()).strip()


def _is_ignored_chain(name: str, chains: list[str], threshold: float = 0.90) -> bool:
    """True if `name` matches a blocklisted chain (prefix or fuzzy ~90%)."""
    n = _normalize_for_chain_match(name)
    for chain in chains:
        c = _normalize_for_chain_match(chain)
        # Prefix match: catches "Brand - Branch Name" patterns
        if n == c or n.startswith(c + " "):
            return True
        # Fuzzy match: catches typos / punctuation variants
        sm = difflib.SequenceMatcher(None, n, c)
        if sm.quick_ratio() >= threshold and sm.ratio() >= threshold:
            return True
    return False


def save_contact(
    name: str,
    city: str,
    *,
    country: str = "DE",
    type: str = "",
    website: str = "",
    email: str = "",
    phone: str = "",
    notes: str = "",
    scan_level: int | None = None,
    status: str = "candidate",
    neighborhood: str = "",
) -> int:
    """
    Insert a new contact (default status 'candidate').
    Returns the new contact's id on insert, or 0 if NOT newly created — i.e. an
    ignored chain, an email duplicate, or a (name, city) duplicate. Callers rely
    on this falsy value to skip/count duplicates rather than re-process a known
    contact.
    """
    with db() as conn:
        cur = conn.cursor()
        # Skip names matching the ignored-chains blocklist
        if _is_ignored_chain(name, _load_ignored_chains(cur)):
            logger.info("save_contact: ignored chain skipped — %s / %s", name, city)
            return 0

        # Email dedup — already have an active contact with this email
        if email:
            cur.execute(
                "SELECT id FROM contacts WHERE lower(email) = lower(%s) AND deleted_at IS NULL",
                (email,),
            )
            if cur.fetchone():
                logger.debug("save_contact: email duplicate skipped — %s (%s)", name, email)
                return 0

        # Name+city dedup
        cur.execute(
            "SELECT id FROM contacts WHERE lower(name) = lower(%s) AND lower(city) = lower(%s)",
            (name, city),
        )
        if cur.fetchone():
            logger.debug("save_contact: duplicate skipped — %s / %s", name, city)
            return 0

        cur.execute(
            """
            INSERT INTO contacts
                (name, city, country, type, website, email, phone, notes, status, scan_level, neighborhood)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, city, country, type or None, website or None, email or None,
             phone or None, notes or None, status, scan_level, neighborhood or None),
        )
        contact_id = cur.fetchone()["id"]
        ensure_consent_log(contact_id, conn=conn)
        logger.info("save_contact: created id=%d  %s / %s", contact_id, name, city)
        return contact_id


def get_candidates(limit: int = 50) -> list[dict]:
    """Return contacts with status='candidate'."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM contacts WHERE status = 'candidate' ORDER BY created_at ASC LIMIT %s",
            (limit,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def get_cold_contacts(
    limit: int = 20,
    city: str | None = None,
    scan_level: int | None = None,
    neighborhood: str | None = None,
    min_tier: str | None = None,
) -> list[dict]:
    """
    Return contacts with status='cold' ready for first outreach, excluding any
    already in the approval queue, best-fit first.

    min_tier: 'normal' excludes tier='poor'; 'wealthy' returns only wealthy.
              NULL-tier contacts are always included unless min_tier is set.
    """
    with db() as conn:
        cur = conn.cursor()
        conditions = ["status = 'cold'", "id NOT IN (SELECT contact_id FROM approval_queue)"]
        params: list = []
        if city:
            conditions.append("lower(city) = lower(%s)")
            params.append(city)
        if scan_level is not None:
            conditions.append("scan_level = %s")
            params.append(scan_level)
        if neighborhood:
            conditions.append("lower(neighborhood) = lower(%s)")
            params.append(neighborhood)
        if min_tier == "normal":
            conditions.append("(neighborhood_tier IS NULL OR neighborhood_tier != 'poor')")
        elif min_tier == "wealthy":
            conditions.append("neighborhood_tier = 'wealthy'")
        params.append(limit)
        where = " AND ".join(conditions)
        cur.execute(
            f"SELECT * FROM contacts WHERE {where} "
            f"ORDER BY fit_score DESC NULLS LAST, created_at ASC LIMIT %s",
            params,
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def update_contact(contact_id: int, status: str, fit_score: int, notes: str = "") -> None:
    """Update a contact's status and fit_score. Appends notes if provided."""
    with db() as conn:
        cur = conn.cursor()
        if notes:
            cur.execute(
                """
                UPDATE contacts
                SET status = %s, fit_score = %s,
                    notes = CASE WHEN notes IS NULL THEN %s ELSE notes || E'\n' || %s END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, fit_score, notes, notes, contact_id),
            )
        else:
            cur.execute(
                "UPDATE contacts SET status = %s, fit_score = %s, updated_at = NOW() WHERE id = %s",
                (status, fit_score, contact_id),
            )


def get_contacts_needing_enrichment(limit: int = 50, city: str | None = None) -> list[dict]:
    """Return contacts missing an email, never-enriched first, skipping dead-ends."""
    with db() as conn:
        cur = conn.cursor()
        conditions = [
            "(email IS NULL OR email = '')",
            "deleted_at IS NULL",
            "status != 'cannot_find_more_data'",
        ]
        params: list = []
        if city:
            conditions.append("lower(city) = lower(%s)")
            params.append(city)
        params.append(limit)
        where = " AND ".join(conditions)
        cur.execute(
            f"SELECT * FROM contacts WHERE {where} "
            f"ORDER BY enriched_at ASC NULLS FIRST, created_at ASC LIMIT %s",
            params,
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def update_contact_details(contact_id: int, **kwargs) -> None:
    """
    Update contact fields (website, email, phone, status). Ignores unknown keys.
    Always stamps enriched_at so the contact counts as processed by enrichment,
    even when no field changed.
    """
    allowed = {"website", "email", "phone", "status"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v}
    set_clause = ", ".join(f"{column} = %s" for column in fields)
    if set_clause:
        set_clause += ", enriched_at = NOW(), updated_at = NOW()"
    else:
        set_clause = "enriched_at = NOW(), updated_at = NOW()"
    values = list(fields.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = %s",
            values,
        )


def match_contact_by_email(from_email: str) -> dict | None:
    """Find a contact by email, with a corporate-domain fallback. None if not found.

    The result carries `_match_type`: "exact" when the address matches a contact
    directly, "domain" when it only matched another contact at the same corporate
    domain. Callers must not let a "domain" match drive irreversible autonomous
    actions (opt-out, bad_email, visit flag) — it may be a colleague, not the
    contact."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM contacts WHERE lower(email) = lower(%s) LIMIT 1",
            (from_email,),
        )
        row = cur.fetchone()
        if row:
            contact = serialize_row(dict(row))
            contact["_match_type"] = "exact"
            return contact
        # Fallback: match any contact at the same corporate domain (not freemail)
        domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
        if domain and domain not in FREEMAIL_DOMAINS:
            cur.execute(
                "SELECT * FROM contacts WHERE lower(email) LIKE lower(%s) LIMIT 1",
                (f"%@{domain}",),
            )
            row = cur.fetchone()
            if row:
                contact = serialize_row(dict(row))
                contact["_match_type"] = "domain"
                return contact
        return None


def get_contact(contact_id: int) -> dict | None:
    """Return a single contact by id (serialized), or None if not found."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        return serialize_row(dict(row)) if row else None


# ---------------------------------------------------------------------------
# GDPR / Compliance
# ---------------------------------------------------------------------------

def ensure_consent_log(contact_id: int, *, conn=None) -> None:
    """
    Create a consent_log entry for a contact if one doesn't exist.
    Can receive an existing connection (when called within save_contact's transaction).
    """
    def _insert(c):
        cur = c.cursor()
        cur.execute(
            "SELECT id FROM consent_log WHERE contact_id = %s LIMIT 1",
            (contact_id,),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO consent_log (contact_id, legal_basis, first_contact_date)
                VALUES (%s, 'legitimate_interest', NOW())
                """,
                (contact_id,),
            )

    if conn:
        _insert(conn)
    else:
        with db() as conn:
            _insert(conn)


def check_compliance(contact_id: int) -> bool:
    """
    Returns True if outreach to this contact is permitted.
    Blocked if: opt_out is set, erasure_requested is set, or contact has been erased.
    """
    with db() as conn:
        cur = conn.cursor()
        # Check consent_log
        cur.execute(
            """
            SELECT opt_out, erasure_requested
            FROM consent_log WHERE contact_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact_id,),
        )
        row = cur.fetchone()
        if row and (row["opt_out"] or row["erasure_requested"]):
            return False
        # Check contact not erased and not do_not_contact
        cur.execute("SELECT name, status FROM contacts WHERE id = %s", (contact_id,))
        contact = cur.fetchone()
        if not contact or contact["name"] == "[removed]":
            return False
        if contact["status"] == "do_not_contact":
            return False
        return True


def set_opt_out(contact_id: int) -> None:
    """Record opt-out in consent_log and update contact status to 'do_not_contact'."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO consent_log (contact_id, legal_basis, opt_out, opt_out_date)
            VALUES (%s, 'legitimate_interest', TRUE, NOW())
            """,
            (contact_id,),
        )
        cur.execute(
            "UPDATE contacts SET status = 'do_not_contact', updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )
        logger.info("set_opt_out: contact_id=%d opted out", contact_id)


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------

def queue_for_approval(contact_id: int, run_id: int, subject: str, body: str) -> int:
    """
    Insert an email draft into the approval queue. Returns queue item id.
    Best-effort: pings registered mobile devices that a new draft is waiting.
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO approval_queue (contact_id, agent_run_id, draft_subject, draft_body)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (contact_id, run_id or None, subject, body),
        )
        queue_id = cur.fetchone()["id"]
        cur.execute("SELECT name FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        contact_name = row["name"] if row else "a contact"

    # Notify mobile devices after the row is committed. Never blocks queueing.
    try:
        from gcrm.api.push import send_push_to_all
        send_push_to_all(
            title="New approval waiting",
            body=f"{contact_name} — {subject}",
            data={"screen": "approvals"},
        )
    except Exception as error:
        logger.debug("approval push notification failed (non-blocking): %s", error)
    return queue_id


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------

def log_interaction(
    contact_id: int,
    method: str,
    direction: str,
    summary: str,
    outcome: str,
) -> None:
    """Log a contact interaction and update the contact's updated_at timestamp."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO interactions
                (contact_id, interaction_date, method, direction, summary, outcome)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
            """,
            (contact_id, method, direction, summary, outcome),
        )
        cur.execute(
            "UPDATE contacts SET updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )


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

def get_contact_interactions(contact_id: int) -> list[dict]:
    """Return all logged interactions for a contact, newest first."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT interaction_date, method, direction, summary, outcome
            FROM interactions
            WHERE contact_id = %s
            ORDER BY interaction_date DESC
            """,
            (contact_id,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


# --- User-account operations live in db_users.py; re-exported here so callers
#     can keep importing them from gcrm.tools.db ---
from gcrm.tools.db_users import (
    get_user_by_email,
    get_user_token_version,
    create_user,
    set_user_password,
    set_user_active,
    list_users,
    touch_user_login,
)


# --- City + scan-level operations live in db_cities.py; re-exported here ---
from gcrm.tools.db_cities import (
    get_cities, get_city_market_context, update_city_market, add_city,
    get_city_scan_status, get_all_city_scan_status, record_scan_result, can_run_level,
)


# --- Outreach quality-loop operations live in db_outreach.py; re-exported here ---
from gcrm.tools.db_outreach import record_warm_outcome, get_outreach_outcomes


# --- Agent-run logging operations live in db_agent_runs.py; re-exported here ---
from gcrm.tools.db_agent_runs import start_run, finish_run, get_run_costs


# --- People operations live in db_people.py; re-exported here ---
from gcrm.tools.db_people import save_person, get_people, get_person


# --- Inbox-message operations live in db_inbox.py; re-exported here ---
from gcrm.tools.db_inbox import (
    save_inbox_message, get_unprocessed_inbox, mark_message_processed,
    save_inbox_classification, mark_bad_email, set_visit_when_nearby,
)
