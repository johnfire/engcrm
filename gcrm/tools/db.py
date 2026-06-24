"""
All database operations used as injected tools in the agents.
Every function uses parameterised queries — no string interpolation on user data.
"""
import difflib
import json
import logging
import re
from datetime import date, datetime, timezone

from gcrm.db.connection import db
from gcrm.tools.email_domains import FREEMAIL_DOMAINS

logger = logging.getLogger(__name__)


def serialize_row(row: dict) -> dict:
    """Convert datetime/date objects to ISO strings so rows are JSON-safe."""
    return {
        key: value.isoformat() if isinstance(value, (datetime, date)) else value
        for key, value in row.items()
    }


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def _load_ignored_chains(cur) -> list[str]:
    cur.execute("SELECT name FROM ignored_chains")
    return [r["name"] for r in cur.fetchall()]


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
        return [serialize_row(dict(r)) for r in cur.fetchall()]


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
        return [serialize_row(dict(r)) for r in cur.fetchall()]


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
        return [serialize_row(dict(r)) for r in cur.fetchall()]


def update_contact_details(contact_id: int, **kwargs) -> None:
    """
    Update contact fields (website, email, phone, status). Ignores unknown keys.
    Always stamps enriched_at so the contact counts as processed by enrichment,
    even when no field changed.
    """
    allowed = {"website", "email", "phone", "status"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v}
    set_clause = ", ".join(f"{k} = %s" for k in fields)
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
        return [dict(r) for r in cur.fetchall()]


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
        return [serialize_row(dict(r)) for r in cur.fetchall()]


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


def save_inbox_classification(
    inbox_message_id: int,
    contact_id: int | None,
    classification: str,
    reasoning: str,
) -> None:
    """Persist the LLM classification + reasoning and mark the message processed."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE inbox_messages
            SET processed = TRUE,
                matched_contact_id = %s,
                classification = %s,
                classification_reasoning = %s
            WHERE id = %s
            """,
            (contact_id, classification, reasoning, inbox_message_id),
        )


def mark_bad_email(contact_id: int) -> None:
    """Mark a contact's email undeliverable: status='bad_email' + log a bounce interaction."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET status = 'bad_email', updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )
        cur.execute(
            """
            INSERT INTO interactions
                (contact_id, interaction_date, method, direction, summary, outcome)
            VALUES (%s, NOW(), 'email', 'inbound', 'Delivery failure — email bounced', 'bounce')
            """,
            (contact_id,),
        )
        logger.info("mark_bad_email: contact_id=%d marked as bad_email", contact_id)


def set_visit_when_nearby(contact_id: int) -> None:
    """Flag a contact for a personal visit next time you're in the area."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET visit_when_nearby = TRUE, updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )
        logger.info("set_visit_when_nearby: contact_id=%d flagged", contact_id)


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
                ) AS scans,
                COALESCE(
                    json_object_agg(emailed.scan_level::text, emailed.cnt)
                        FILTER (WHERE emailed.scan_level IS NOT NULL),
                    '{}'
                ) AS emailed_by_level,
                COALESCE(live.cnt, 0) AS total_contacts
            FROM cities ci
            LEFT JOIN city_scans cs ON cs.city_id = ci.id
            LEFT JOIN (
                SELECT lower(city) AS city_lower, scan_level, COUNT(*) AS cnt
                FROM contacts
                WHERE status IN ('contacted', 'meeting', 'proposal', 'accepted')
                  AND scan_level IS NOT NULL
                GROUP BY lower(city), scan_level
            ) emailed ON lower(ci.city) = emailed.city_lower
            LEFT JOIN (
                SELECT lower(city) AS city_lower, COUNT(*) AS cnt
                FROM contacts
                GROUP BY lower(city)
            ) live ON lower(ci.city) = live.city_lower
            GROUP BY ci.id, ci.city, ci.country, ci.region, live.cnt
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
        return [serialize_row(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Agent run logging
# ---------------------------------------------------------------------------

def start_run(agent_name: str, input_data: dict) -> int:
    """Insert a new agent_run record. Returns run_id. Resets per-run cost counters."""
    from gcrm.tools.costs import reset_costs
    reset_costs()
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
    """Update an agent_run record with completion details + record run costs."""
    from gcrm.tools.costs import get_costs, format_costs
    costs = get_costs()
    cost_line = format_costs()
    full_summary = f"{summary} | {cost_line}" if summary else cost_line
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE agent_runs
            SET status = %s, summary = %s, output_json = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (status, full_summary, json.dumps(output_data, default=str), run_id),
        )
        cur.execute(
            """
            INSERT INTO run_costs (run_id, search_queries, llm_usage_json, total_usd)
            VALUES (%s, %s, %s, %s)
            """,
            (
                run_id,
                costs["breakdown"].get("web_search", {}).get("queries", 0),
                json.dumps({k: v for k, v in costs["breakdown"].items() if k != "web_search"}),
                costs["total_usd"],
            ),
        )


def get_run_costs(limit: int = 20) -> list[dict]:
    """Return recent run costs joined with agent_run summaries."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                rc.run_id, ar.agent_name, ar.started_at, ar.finished_at,
                rc.search_queries, rc.llm_usage_json, rc.total_usd
            FROM run_costs rc
            JOIN agent_runs ar ON ar.id = rc.run_id
            ORDER BY rc.recorded_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [serialize_row(dict(r)) for r in cur.fetchall()]


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
        return [serialize_row(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Users (web UI authentication)
# ---------------------------------------------------------------------------

def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email (case-insensitive). Returns None if absent."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, password_hash, role, is_active, token_version "
            "FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        return cur.fetchone()


def get_user_token_version(user_id: int) -> int | None:
    """Current token version for an ACTIVE user, or None if the user is missing
    or disabled. A None or mismatch revokes the caller's bearer token."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT token_version FROM users WHERE id = %s AND is_active = TRUE",
            (user_id,),
        )
        row = cur.fetchone()
        return row["token_version"] if row else None


def create_user(email: str, password_hash: str, role: str = "admin", name: str = "") -> int:
    """Insert a new user and return its id. Raises on duplicate email."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, name, password_hash, role) "
            "VALUES (LOWER(%s), %s, %s, %s) RETURNING id",
            (email, name, password_hash, role),
        )
        return cur.fetchone()["id"]


def set_user_password(email: str, password_hash: str) -> bool:
    """Update a user's password hash. Returns False if no such user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s, token_version = token_version + 1 "
            "WHERE LOWER(email) = LOWER(%s)",
            (password_hash, email),
        )
        return cur.rowcount > 0


def set_user_active(email: str, is_active: bool) -> bool:
    """Enable or disable a user. Returns False if no such user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_active = %s, token_version = token_version + 1 "
            "WHERE LOWER(email) = LOWER(%s)",
            (is_active, email),
        )
        return cur.rowcount > 0


def list_users() -> list[dict]:
    """All users, newest first, without password hashes."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, role, is_active, created_at, last_login_at "
            "FROM users ORDER BY created_at DESC"
        )
        return [serialize_row(dict(r)) for r in cur.fetchall()]


def touch_user_login(user_id: int) -> None:
    """Record a successful login timestamp for a user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
