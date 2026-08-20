"""Contact persistence tools."""

import difflib
import logging
import re

from psycopg2.extras import Json

from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import (
    DEFAULT_STAGE,
    DEFAULT_STATUS,
    SUPPRESSION_FLAGS,
    coerce_stage,
    coerce_status,
    is_typical,
)
from gcrm.tools.db_approvals import ensure_consent_log
from gcrm.tools.db_audit import log_audit
from gcrm.tools.email_domains import FREEMAIL_DOMAINS
from gcrm.workspace_context import get_workspace_id

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


def save_organization(
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
    pipeline_stage: str = DEFAULT_STAGE,
    status: str = DEFAULT_STATUS,
    research_exhausted: bool = False,
    neighborhood: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    google: dict | None = None,
) -> int:
    """
    Insert a new contact (a fresh `candidate` with nothing going on by default).

    `research_exhausted=True` records that the research agent could find no web
    presence at all — a fact about the data, not a pipeline position, so the
    contact still enters as a candidate someone can work by hand.
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
            logger.info("save_organization: ignored chain skipped — %s / %s", name, city)
            return 0

        # Email dedup — already have an active contact with this email
        if email:
            cur.execute(
                "SELECT id FROM contacts WHERE lower(email) = lower(%s) AND deleted_at IS NULL",
                (email,),
            )
            if cur.fetchone():
                logger.debug("save_organization: email duplicate skipped — %s (%s)", name, email)
                return 0

        # Name+city dedup
        cur.execute(
            "SELECT id FROM contacts WHERE lower(name) = lower(%s) AND lower(city) = lower(%s)",
            (name, city),
        )
        if cur.fetchone():
            logger.debug("save_organization: duplicate skipped — %s / %s", name, city)
            return 0

        cur.execute(
            """
            INSERT INTO contacts
                (name, city, country, type, website, email, phone, notes,
                 pipeline_stage, status, research_exhausted,
                 scan_level, neighborhood, latitude, longitude,
                 business_status, rating, user_ratings, google_data, workspace_id)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default'))
            )
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
                coerce_stage(pipeline_stage),
                coerce_status(status),
                research_exhausted,
                scan_level,
                neighborhood or None,
                latitude,
                longitude,
                business_status or None,
                rating,
                user_ratings,
                google_json,
                get_workspace_id(),
            ),
        )
        contact_id = cur.fetchone()["id"]
        ensure_consent_log(contact_id, conn=conn)
        logger.info("save_organization: created id=%d  %s / %s", contact_id, name, city)
    log_audit(None, None, "contact.created", f"contact:{contact_id}", "created")
    return contact_id


def get_existing_organization_names(city: str, country: str = "DE") -> set[str]:
    """Lowercased names of contacts already saved for a city — the research
    agent's 'already scanned' set, so each scan only processes new businesses."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT lower(name) AS name FROM contacts WHERE lower(city) = lower(%s)", (city,)
        )
        return {row["name"] for row in cur.fetchall()}


def update_organization_google_data(contact_id: int, google: dict) -> None:
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
    """Return contacts still at the 'candidate' stage — not yet evaluated."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM contacts WHERE pipeline_stage = 'candidate' "
            "AND deleted_at IS NULL ORDER BY created_at ASC LIMIT %s",
            (limit,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def get_organizations_ready_for_outreach(
    limit: int = 20,
    city: str | None = None,
    scan_level: int | None = None,
    neighborhood: str | None = None,
    min_tier: str | None = None,
) -> list[dict]:
    """
    Return contacts with status='ready' — scored a fit, first email not yet
    sent — excluding any already in the approval queue, best-fit first.

    Suppression is filtered here explicitly. It used to be implicit: an opt-out
    or a bounce overwrote the status, so a suppressed contact could not also be
    'cold'. Now that those are flags that survive any status, this query is the
    thing standing between an opted-out organization and another email.

    min_tier: 'normal' excludes tier='poor'; 'wealthy' returns only wealthy.
              NULL-tier contacts are always included unless min_tier is set.
    """
    with db() as conn:
        cur = conn.cursor()
        conditions = [
            "status = 'ready'",
            "do_not_contact = FALSE",
            "email_bounced = FALSE",
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


def set_organization_state(
    contact_id: int,
    *,
    pipeline_stage: str,
    status: str,
    fit_score: int | None = None,
    notes: str = "",
) -> None:
    """Move a contact to a pipeline stage and a current status, together.

    The two are written in one statement because they describe one decision —
    "this is a suspect and it is ready for outreach" — and a half-applied move
    leaves a contact somewhere that makes no sense.
    """
    stage, current_status = coerce_stage(pipeline_stage), coerce_status(status)
    if not is_typical(stage, current_status):
        logger.info(
            "contact %d moved to an unusual combination: stage=%s status=%s",
            contact_id, stage, current_status,
        )
    with db() as conn:
        cur = conn.cursor()
        if notes:
            cur.execute(
                """
                UPDATE contacts
                SET pipeline_stage = %s, status = %s,
                    fit_score = COALESCE(%s, fit_score),
                    notes = CASE WHEN notes IS NULL THEN %s ELSE notes || E'\n' || %s END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (stage, current_status, fit_score, notes, notes, contact_id),
            )
        else:
            cur.execute(
                """
                UPDATE contacts
                SET pipeline_stage = %s, status = %s,
                    fit_score = COALESCE(%s, fit_score), updated_at = NOW()
                WHERE id = %s
                """,
                (stage, current_status, fit_score, contact_id),
            )
    log_audit(None, None, "contact.state_changed", f"contact:{contact_id}", f"{stage}/{current_status}")


def set_suppression_flag(contact_id: int, flag: str, value: bool = True) -> None:
    """Raise or clear one suppression fact about a contact.

    Suppression is deliberately not a status: an organization can be at
    `meeting` and have a bounced address at the same time, and recording the
    bounce must not cost you the meeting. The flag name is checked against
    SUPPRESSION_FLAGS before it reaches SQL — it is interpolated into the
    statement, so an unchecked name would be an injection point.
    """
    if flag not in SUPPRESSION_FLAGS:
        raise ValueError(f"unknown suppression flag: {flag!r}")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {flag} = %s, updated_at = NOW() WHERE id = %s",
            (value, contact_id),
        )
    logger.info("contact %d: %s = %s", contact_id, flag, value)
    log_audit(None, None, f"contact.{flag}", f"contact:{contact_id}", str(value).lower())


def get_organizations_needing_enrichment(limit: int = 50, city: str | None = None) -> list[dict]:
    """Return contacts missing an email, never-enriched first, skipping dead-ends."""
    with db() as conn:
        cur = conn.cursor()
        conditions = [
            "(email IS NULL OR email = '')",
            "deleted_at IS NULL",
            "research_exhausted = FALSE",
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


def update_organization_details(contact_id: int, **kwargs) -> None:
    """
    Update contact detail fields (website, email, phone). Ignores unknown keys.
    Always stamps enriched_at so the contact counts as processed by enrichment,
    even when no field changed.

    Pipeline position is not a detail: use set_organization_state. Suppression is not
    a detail either: use set_suppression_flag.
    """
    allowed = {"website", "email", "phone"}
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


def match_organization_by_email(from_email: str) -> dict | None:
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
            organization = serialize_row(dict(row))
            organization["_match_type"] = "exact"
            return organization
        # Fallback: match any contact at the same corporate domain (not freemail)
        domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
        if domain and domain not in FREEMAIL_DOMAINS:
            cur.execute(
                "SELECT * FROM contacts WHERE lower(email) LIKE lower(%s) LIMIT 1",
                (f"%@{domain}",),
            )
            row = cur.fetchone()
            if row:
                organization = serialize_row(dict(row))
                organization["_match_type"] = "domain"
                return organization
        return None


def get_organization(contact_id: int) -> dict | None:
    """Return a single contact by id (serialized), or None if not found."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        return serialize_row(dict(row)) if row else None
