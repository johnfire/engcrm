"""
All database operations used as injected tools in the agents.
Every function uses parameterised queries — no string interpolation on user data.
"""
import json
import logging
from datetime import date, datetime, timezone

from gcrm.db.connection import db

logger = logging.getLogger(__name__)


def _serialize_row(row: dict) -> dict:
    """Convert datetime/date objects to ISO strings so rows are JSON-safe."""
    return {
        k: v.isoformat() if isinstance(v, (datetime, date)) else v
        for k, v in row.items()
    }


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

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
) -> int:
    """
    Insert a new contact with status='candidate'.
    Deduplication key is (name, city). Returns the new contact's id on insert,
    or 0 if the contact already exists (duplicate) or on error. A 0 return means
    "not newly created" — callers rely on this falsy value to skip/count
    duplicates rather than re-process an already-known contact.
    """
    with db() as conn:
        cur = conn.cursor()
        # Check for duplicate
        cur.execute(
            "SELECT id FROM contacts WHERE lower(name) = lower(%s) AND lower(city) = lower(%s)",
            (name, city),
        )
        existing = cur.fetchone()
        if existing:
            logger.debug("save_contact: duplicate skipped — %s / %s", name, city)
            return 0

        cur.execute(
            """
            INSERT INTO contacts (name, city, country, type, website, email, phone, notes, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'candidate')
            RETURNING id
            """,
            (name, city, country, type or None, website or None, email or None, phone or None, notes or None),
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
        return [_serialize_row(dict(r)) for r in cur.fetchall()]


def get_cold_contacts(limit: int = 20) -> list[dict]:
    """Return contacts with status='cold' ready for first outreach."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM contacts WHERE status = 'cold' ORDER BY created_at ASC LIMIT %s",
            (limit,),
        )
        return [_serialize_row(dict(r)) for r in cur.fetchall()]


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


def get_contacts_needing_enrichment(limit: int = 50) -> list[dict]:
    """Return contacts missing both website and email, any status."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM contacts
            WHERE (website IS NULL OR website = '')
              AND (email IS NULL OR email = '')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [_serialize_row(dict(r)) for r in cur.fetchall()]


def update_contact_details(contact_id: int, **kwargs) -> None:
    """Update arbitrary contact fields (website, email, phone). Ignores unknown keys."""
    allowed = {"website", "email", "phone"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {set_clause}, updated_at = NOW() WHERE id = %s",
            values,
        )


def match_contact_by_email(from_email: str) -> dict | None:
    """Find a contact by email address. Returns None if not found."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM contacts WHERE lower(email) = lower(%s) LIMIT 1",
            (from_email,),
        )
        row = cur.fetchone()
        return _serialize_row(dict(row)) if row else None


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
        with db() as c:
            _insert(c)


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
    """Insert an email draft into the approval queue. Returns queue item id."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO approval_queue (contact_id, agent_run_id, draft_subject, draft_body)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (contact_id, run_id or None, subject, body),
        )
        return cur.fetchone()["id"]


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
        return [_serialize_row(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Inbox messages
# ---------------------------------------------------------------------------

def save_inbox_message(
    message_id: str,
    from_email: str,
    subject: str,
    body: str,
    received_at: datetime,
) -> int:
    """Cache an inbox message from IMAP. Returns id, or 0 if duplicate."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM inbox_messages WHERE message_id = %s",
            (message_id,),
        )
        if cur.fetchone():
            return 0
        cur.execute(
            """
            INSERT INTO inbox_messages (message_id, from_email, subject, body, received_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (message_id, from_email, subject, body, received_at),
        )
        return cur.fetchone()["id"]


def get_unprocessed_inbox() -> list[dict]:
    """Return inbox messages not yet processed by the follow-up agent."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM inbox_messages WHERE processed = FALSE ORDER BY received_at ASC"
        )
        return [dict(r) for r in cur.fetchall()]


def mark_message_processed(inbox_message_id: int, contact_id: int | None) -> None:
    """Mark an inbox message as processed, linking it to a contact if matched."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE inbox_messages
            SET processed = TRUE, matched_contact_id = %s
            WHERE id = %s
            """,
            (contact_id, inbox_message_id),
        )


# ---------------------------------------------------------------------------
# Cities + scan levels
# ---------------------------------------------------------------------------

def get_cities(country: str = "") -> list[dict]:
    """Return all cities, optionally filtered by country."""
    with db() as conn:
        cur = conn.cursor()
        if country:
            cur.execute(
                "SELECT * FROM cities WHERE country = %s ORDER BY city",
                (country,),
            )
        else:
            cur.execute("SELECT * FROM cities ORDER BY city, country")
        return [dict(r) for r in cur.fetchall()]


def get_city_market_context(city: str, country: str = "DE") -> dict:
    """Return market_character and market_notes for a city. Returns empty dict if not found."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT market_character, market_notes FROM cities WHERE lower(city) = lower(%s) AND country = %s",
            (city, country.upper()),
        )
        row = cur.fetchone()
        return dict(row) if row else {"market_character": "unknown", "market_notes": ""}


def update_city_market(city: str, country: str = "DE", character: str = "", notes: str = "") -> bool:
    """Update market_character and/or market_notes for a city. Returns True if found."""
    with db() as conn:
        cur = conn.cursor()
        if character and notes:
            cur.execute(
                "UPDATE cities SET market_character = %s, market_notes = %s WHERE lower(city) = lower(%s) AND country = %s",
                (character, notes, city, country.upper()),
            )
        elif character:
            cur.execute(
                "UPDATE cities SET market_character = %s WHERE lower(city) = lower(%s) AND country = %s",
                (character, city, country.upper()),
            )
        elif notes:
            cur.execute(
                "UPDATE cities SET market_notes = %s WHERE lower(city) = lower(%s) AND country = %s",
                (notes, city, country.upper()),
            )
        return cur.rowcount > 0


def add_city(city: str, country: str = "DE", region: str = "") -> int:
    """Add a city to the master list. Returns city_id. Safe to call if already exists."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cities (city, country, region)
            VALUES (%s, %s, %s)
            ON CONFLICT (city, country) DO UPDATE SET region = EXCLUDED.region
            RETURNING id
            """,
            (city, country, region),
        )
        return cur.fetchone()["id"]


def get_city_scan_status(city: str, country: str = "DE") -> list[dict]:
    """Return scan records for a city across all levels."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cs.level, cs.last_run_at, cs.contacts_found, cs.run_count, cs.due_for_rerun
            FROM city_scans cs
            JOIN cities ci ON ci.id = cs.city_id
            WHERE LOWER(ci.city) = LOWER(%s) AND ci.country = %s
            ORDER BY cs.level
            """,
            (city, country),
        )
        return [dict(r) for r in cur.fetchall()]


def get_all_city_scan_status() -> list[dict]:
    """Return all cities with their scan status across all levels."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                ci.id, ci.city, ci.country, ci.region,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'level', cs.level,
                            'last_run_at', cs.last_run_at,
                            'contacts_found', cs.contacts_found,
                            'run_count', cs.run_count,
                            'due_for_rerun', cs.due_for_rerun
                        ) ORDER BY cs.level
                    ) FILTER (WHERE cs.level IS NOT NULL),
                    '[]'
                ) AS scans
            FROM cities ci
            LEFT JOIN city_scans cs ON cs.city_id = ci.id
            GROUP BY ci.id, ci.city, ci.country, ci.region
            ORDER BY ci.city, ci.country
            """,
        )
        return [dict(r) for r in cur.fetchall()]


def record_scan_result(city: str, country: str, level: int, contacts_found: int) -> None:
    """Record the result of a completed scan. Creates or updates the city_scans row."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM cities WHERE LOWER(city) = LOWER(%s) AND country = %s", (city, country))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO cities (city, country) VALUES (%s, %s) RETURNING id",
                (city, country),
            )
            row = cur.fetchone()
        city_id = row["id"]
        cur.execute(
            """
            INSERT INTO city_scans (city_id, level, last_run_at, contacts_found, run_count)
            VALUES (%s, %s, NOW(), %s, 1)
            ON CONFLICT (city_id, level) DO UPDATE
                SET last_run_at = NOW(),
                    contacts_found = city_scans.contacts_found + EXCLUDED.contacts_found,
                    run_count = city_scans.run_count + 1,
                    due_for_rerun = FALSE
            """,
            (city_id, level, contacts_found),
        )


def can_run_level(city: str, country: str, level: int) -> tuple[bool, str]:
    """
    Check if a scan level can be run on a city.
    Level 1 can always run. All others require level 1 to be completed first.
    Returns (allowed, reason).
    """
    if level == 1:
        return True, ""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cs.level FROM city_scans cs
            JOIN cities ci ON ci.id = cs.city_id
            WHERE LOWER(ci.city) = LOWER(%s) AND ci.country = %s AND cs.level = 1
            """,
            (city, country),
        )
        if not cur.fetchone():
            return False, f"Level 1 must be run on {city} first"
    return True, ""


# ---------------------------------------------------------------------------
# Research queue (legacy — kept for reference, not used by new system)
# ---------------------------------------------------------------------------

def get_next_research_targets(cities_per_run: int = 3) -> list[dict]:
    """Legacy function — returns next batch from old research_queue table."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT city, country,
                   MIN(COALESCE(last_run_at, '1970-01-01')) AS oldest
            FROM research_queue
            GROUP BY city, country
            ORDER BY oldest ASC
            LIMIT %s
            """,
            (cities_per_run,),
        )
        cities = [(r["city"], r["country"]) for r in cur.fetchall()]
        if not cities:
            return []
        targets = []
        for city, country in cities:
            cur.execute(
                "SELECT city, industry, country FROM research_queue WHERE city = %s AND country = %s",
                (city, country),
            )
            targets.extend([dict(r) for r in cur.fetchall()])
        return targets


def mark_research_target_done(city: str, industry: str) -> None:
    """Legacy function — updates old research_queue table."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE research_queue
            SET last_run_at = NOW(), run_count = run_count + 1
            WHERE city = %s AND industry = %s
            """,
            (city, industry),
        )


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
        return [_serialize_row(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Agent run logging
# ---------------------------------------------------------------------------

def start_run(agent_name: str, input_data: dict) -> int:
    """Insert a new agent_run record. Returns run_id."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO agent_runs (agent_name, status, input_json)
            VALUES (%s, 'running', %s) RETURNING id
            """,
            (agent_name, json.dumps(input_data, default=str)),
        )
        return cur.fetchone()["id"]


def finish_run(run_id: int, status: str, summary: str, output_data: dict) -> None:
    """Update an agent_run record with completion details."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE agent_runs
            SET status = %s, summary = %s, output_json = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (status, summary, json.dumps(output_data, default=str), run_id),
        )


# ---------------------------------------------------------------------------
# Outreach quality loop
# ---------------------------------------------------------------------------

def record_warm_outcome(contact_id: int) -> None:
    """
    Record that a contact sent a warm/interested reply.
    Looks up the most recent outbound and inbound interactions for the contact,
    and the most recently approved queue item for word count.
    Silently skips if no outbound interaction exists yet.
    """
    with db() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id FROM interactions
            WHERE contact_id = %s AND direction = 'outbound' AND method = 'email'
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact_id,),
        )
        sent_row = cur.fetchone()
        if not sent_row:
            logger.info("record_warm_outcome: no outbound interaction found for contact_id=%d — skipping", contact_id)
            return
        sent_interaction_id = sent_row["id"]

        cur.execute(
            """
            SELECT id FROM interactions
            WHERE contact_id = %s AND direction = 'inbound' AND method = 'email'
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact_id,),
        )
        reply_row = cur.fetchone()
        reply_interaction_id = reply_row["id"] if reply_row else None

        cur.execute(
            """
            SELECT draft_body FROM approval_queue
            WHERE contact_id = %s AND status IN ('approved', 'approved_unsent')
            ORDER BY COALESCE(reviewed_at, created_at) DESC LIMIT 1
            """,
            (contact_id,),
        )
        queue_row = cur.fetchone()
        word_count = len(queue_row["draft_body"].split()) if queue_row else None

        cur.execute(
            """
            INSERT INTO outreach_outcomes
                (contact_id, sent_interaction_id, reply_interaction_id, warm, word_count)
            VALUES (%s, %s, %s, true, %s)
            ON CONFLICT (sent_interaction_id) DO NOTHING
            """,
            (contact_id, sent_interaction_id, reply_interaction_id, word_count),
        )
        logger.info("record_warm_outcome: recorded for contact_id=%d word_count=%s", contact_id, word_count)


def get_outreach_outcomes(days: int = 90) -> list[dict]:
    """Return outreach_outcomes with sent email bodies for the last N days."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                oo.id, oo.contact_id, oo.warm, oo.word_count, oo.created_at,
                aq.draft_subject, aq.draft_body,
                c.name AS contact_name, c.city, c.type AS contact_type
            FROM outreach_outcomes oo
            JOIN contacts c ON c.id = oo.contact_id
            LEFT JOIN LATERAL (
                SELECT draft_subject, draft_body
                FROM approval_queue
                WHERE contact_id = oo.contact_id
                  AND status IN ('approved', 'approved_unsent')
                ORDER BY COALESCE(reviewed_at, created_at) DESC
                LIMIT 1
            ) aq ON true
            WHERE oo.created_at >= NOW() - %s * INTERVAL '1 day'
            ORDER BY oo.created_at DESC
            """,
            (days,),
        )
        return [_serialize_row(dict(r)) for r in cur.fetchall()]
