"""Contact persistence tools."""

import difflib
import logging
import re

from psycopg2.extras import Json

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_approvals import ensure_consent_log
from gcrm.tools.db_audit import log_audit
from gcrm.tools.email_domains import FREEMAIL_DOMAINS

logger = logging.getLogger(__name__)


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


def _google_columns(google: dict) -> dict:
    """Map a google_maps_search result to the contact columns we persist."""
    location = google.get("location") or {}
    return {
        "latitude": google.get("latitude")
        if google.get("latitude") is not None
        else location.get("latitude"),
        "longitude": google.get("longitude")
        if google.get("longitude") is not None
        else location.get("longitude"),
        "business_status": google.get("business_status") or "",
        "rating": google.get("rating"),
        "user_ratings": google.get("user_ratings"),
        "google_data": google.get("google_data") or google,
    }


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
    latitude: float | None = None,
    longitude: float | None = None,
    google: dict | None = None,
) -> int:
    """
    Insert a new contact (default status 'candidate').
    Returns the new contact's id on insert, or 0 if NOT newly created — i.e. an
    ignored chain, an email duplicate, or a (name, city) duplicate. Callers rely
    on this falsy value to skip/count duplicates rather than re-process a known
    contact.
    """
    business_status = rating = user_ratings = google_json = None
    if google:
        cols = _google_columns(google)
        if cols["latitude"] is not None:
            latitude = cols["latitude"]
        if cols["longitude"] is not None:
            longitude = cols["longitude"]
        business_status, rating, user_ratings = (
            cols["business_status"],
            cols["rating"],
            cols["user_ratings"],
        )
        google_json = Json(cols["google_data"])
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
                (name, city, country, type, website, email, phone, notes, status,
                 scan_level, neighborhood, latitude, longitude,
                 business_status, rating, user_ratings, google_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                name,
                city,
                country,
                type or None,
                website or None,
                email or None,
                phone or None,
                notes or None,
                status,
                scan_level,
                neighborhood or None,
                latitude,
                longitude,
                business_status or None,
                rating,
                user_ratings,
                google_json,
            ),
        )
        contact_id = cur.fetchone()["id"]
        ensure_consent_log(contact_id, conn=conn)
        logger.info("save_contact: created id=%d  %s / %s", contact_id, name, city)
    log_audit(None, None, "contact.created", f"contact:{contact_id}", "created")
    return contact_id


def get_existing_contact_names(city: str, country: str = "DE") -> set[str]:
    """Lowercased names of contacts already saved for a city — the research
    agent's 'already scanned' set, so each scan only processes new businesses."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT lower(name) AS name FROM contacts WHERE lower(city) = lower(%s)", (city,)
        )
        return {row["name"] for row in cur.fetchall()}


def update_contact_google_data(contact_id: int, google: dict) -> None:
    """Attach Google Places data (coords + status/rating + full payload) to an
    existing contact — used by the backfill for contacts saved before geo capture."""
    cols = _google_columns(google)
    with db() as conn:
        conn.cursor().execute(
            """
            UPDATE contacts SET latitude = %s, longitude = %s, business_status = %s,
                rating = %s, user_ratings = %s, google_data = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (
                cols["latitude"],
                cols["longitude"],
                cols["business_status"] or None,
                cols["rating"],
                cols["user_ratings"],
                Json(cols["google_data"]),
                contact_id,
            ),
        )


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
        conditions = [
            "status = 'cold'",
            "deleted_at IS NULL",
            "id NOT IN (SELECT contact_id FROM approval_queue)",
        ]
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
    log_audit(None, None, "contact.scored", f"contact:{contact_id}", status)


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
    log_audit(None, None, "contact.enriched", f"contact:{contact_id}", "updated")


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
