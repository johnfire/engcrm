"""
LinkedIn connection database operations: importing Connections.csv rows as
people, suggesting which of our organizations each connection works at, and
answering "who do I know at this organization?".

Every per-row write runs inside its own SAVEPOINT, so one bad row is counted
and skipped instead of aborting the whole import.
"""
import logging
from contextlib import contextmanager

from gcrm.db.connection import db, serialize_row
from gcrm.linkedin import (
    CompanyPlan,
    OrgIndex,
    linkedin_url_hash,
    normalize_company,
    plan_company_promotion,
)
from gcrm.workspace_context import get_workspace_id

logger = logging.getLogger(__name__)

IMPORT_SOURCE = "linkedin_import"


@contextmanager
def _savepoint(cur):
    cur.execute("SAVEPOINT linkedin_row")
    try:
        yield
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT linkedin_row")
        raise
    else:
        cur.execute("RELEASE SAVEPOINT linkedin_row")


def _find_existing_person(cur, row: dict) -> int | None:
    """The person this connection already is, if we have them: same LinkedIn
    URL, else same email, else same name plus one corroborating fact — the same
    company, or the same connected-on date. A name alone is not enough: two
    different 'Michael Schmidt's must stay two people. The date matters for
    connections with no URL, no email and a placeholder company ("Self-employed"),
    which would otherwise be duplicated by every re-import."""
    if row["linkedin_url"]:
        cur.execute("SELECT id FROM people WHERE lower(linkedin_url) = %s", (row["linkedin_url"],))
        found = cur.fetchone()
        if found:
            return found["id"]
    if row["email"]:
        cur.execute("SELECT id FROM people WHERE lower(email) = lower(%s)", (row["email"],))
        found = cur.fetchone()
        if found:
            return found["id"]
    wanted_company = normalize_company(row["company"])
    wanted_raw = (row["company"] or "").strip().lower()
    cur.execute(
        "SELECT p.id, p.company_raw, p.connected_on, c.name AS company "
        "FROM people p LEFT JOIN contacts c ON c.id = p.contact_id "
        "WHERE lower(p.name) = lower(%s) AND p.linkedin_url IS NULL ORDER BY p.id",
        (row["name"],),
    )
    for candidate in cur.fetchall():
        known = normalize_company(candidate["company_raw"] or candidate["company"])
        same_company = bool(wanted_company) and known == wanted_company
        same_raw = bool(wanted_raw) and (candidate["company_raw"] or "").strip().lower() == wanted_raw
        same_date = row["connected_on"] is not None and candidate["connected_on"] == row["connected_on"]
        if same_company or same_raw or same_date:
            return candidate["id"]
    return None


def _is_suppressed(cur, row: dict) -> bool:
    """True for a connection someone deleted by hand: their URL hash is on the
    suppression list, so the import must not bring them back."""
    url_hash = linkedin_url_hash(row["linkedin_url"])
    if not url_hash:
        return False
    cur.execute("SELECT 1 FROM person_import_suppressions WHERE linkedin_url_hash = %s", (url_hash,))
    return cur.fetchone() is not None


def _upsert_connection(cur, row: dict) -> str:
    """Write one connection. Existing people are marked and have only their
    blank fields filled — nothing you typed is overwritten. Returns 'created'
    or 'updated'."""
    person_id = _find_existing_person(cur, row)
    if person_id is not None:
        cur.execute(
            """
            UPDATE people SET
                is_linkedin_contact = TRUE,
                linkedin_url = COALESCE(NULLIF(linkedin_url, ''), %s),
                connected_on = COALESCE(connected_on, %s),
                company_raw  = COALESCE(NULLIF(company_raw, ''), %s),
                title        = COALESCE(NULLIF(title, ''), %s),
                email        = COALESCE(NULLIF(email, ''), %s),
                updated_at   = NOW()
            WHERE id = %s
            """,
            (row["linkedin_url"], row["connected_on"], row["company"] or None,
             row["title"] or None, row["email"] or None, person_id),
        )
        return "updated"
    cur.execute(
        """
        INSERT INTO people
            (name, title, email, country, source, is_linkedin_contact,
             linkedin_url, connected_on, company_raw, workspace_id)
        VALUES (
            %s, %s, %s, NULL, %s, TRUE, %s, %s, %s,
            COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default'))
        )
        """,
        (row["name"], row["title"] or None, row["email"] or None, IMPORT_SOURCE,
         row["linkedin_url"], row["connected_on"], row["company"] or None,
         get_workspace_id()),
    )
    return "created"


def import_connections(rows: list[dict]) -> dict:
    """Import parsed Connections.csv rows. Idempotent: re-importing a fresh
    export marks/updates the same people instead of duplicating them. Returns
    counts — created, updated, failed, suppressed (skipped because deleted earlier)."""
    counts = {"created": 0, "updated": 0, "failed": 0, "suppressed": 0}
    with db() as conn:
        cur = conn.cursor()
        for row in rows:
            try:
                with _savepoint(cur):
                    if _is_suppressed(cur, row):
                        counts["suppressed"] += 1
                        continue
                    counts[_upsert_connection(cur, row)] += 1
            except Exception:
                counts["failed"] += 1
                logger.warning("linkedin import: row failed for %r", row.get("name"), exc_info=True)
    logger.info("linkedin import: %s", counts)
    return counts


def get_match_suggestions() -> list[dict]:
    """LinkedIn people with a company string but no organization link, each
    with the organizations that string plausibly names. People whose only
    candidates were rejected earlier are left out. Exact, unambiguous matches
    come first."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, title, company_raw, linkedin_url FROM people "
            "WHERE is_linkedin_contact AND contact_id IS NULL AND deleted_at IS NULL "
            "AND COALESCE(company_raw, '') <> '' ORDER BY name"
        )
        people = [dict(row) for row in cur.fetchall()]
        if not people:
            return []
        cur.execute(
            "SELECT id, name, city, status FROM contacts WHERE deleted_at IS NULL"
        )
        organizations = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT person_id, contact_id FROM person_match_rejections")
        rejected = {(row["person_id"], row["contact_id"]) for row in cur.fetchall()}

    index = OrgIndex(organizations)
    status_by_id = {org["id"]: org.get("status") for org in organizations}
    suggestions = []
    for person in people:
        matches = [
            match for match in index.match(person["company_raw"])
            if (person["id"], match.contact_id) not in rejected
        ]
        if matches:
            suggestions.append({
                **person,
                "matches": [
                    {"contact_id": m.contact_id, "name": m.name, "city": m.city,
                     "confidence": m.confidence, "status": status_by_id.get(m.contact_id)}
                    for m in matches
                ],
            })
    order = {"exact": 0, "ambiguous": 1, "partial": 2, "fuzzy": 3}
    suggestions.sort(key=lambda s: (order[s["matches"][0]["confidence"]], s["name"].lower()))
    return suggestions


def apply_match_decisions(decisions: list[dict]) -> dict:
    """Apply the review page's choices. Each decision is
    {person_id, contact_id | None, rejected: [contact_id, ...]}: link the person
    to `contact_id` when given, and remember every id in `rejected` so it is
    never suggested for that person again. Returns counts — linked, rejected,
    failed."""
    counts = {"linked": 0, "rejected": 0, "failed": 0}
    with db() as conn:
        cur = conn.cursor()
        for decision in decisions:
            try:
                with _savepoint(cur):
                    if decision.get("contact_id") is not None:
                        cur.execute(
                            "UPDATE people SET contact_id = %s, updated_at = NOW() "
                            "WHERE id = %s AND is_linkedin_contact "
                            "AND EXISTS (SELECT 1 FROM contacts WHERE id = %s AND deleted_at IS NULL)",
                            (decision["contact_id"], decision["person_id"], decision["contact_id"]),
                        )
                        if cur.rowcount:
                            counts["linked"] += 1
                    for contact_id in decision.get("rejected") or []:
                        cur.execute(
                            "INSERT INTO person_match_rejections (person_id, contact_id) "
                            "SELECT p.id, c.id FROM people p, contacts c "
                            "WHERE p.id = %s AND c.id = %s ON CONFLICT DO NOTHING",
                            (decision["person_id"], contact_id),
                        )
                        counts["rejected"] += cur.rowcount
            except Exception:
                counts["failed"] += 1
                logger.warning("linkedin match: decision failed %r", decision, exc_info=True)
    logger.info("linkedin match decisions: %s", counts)
    return counts


def get_linkedin_connections_for_org(contact_id: int) -> dict:
    """Who do I know at this organization? `linked` are LinkedIn people confirmed
    at it; `possible` are unlinked LinkedIn people whose company string looks
    like its name — shown as unconfirmed, because a walk-in notice that is
    sometimes wrong beats none, as long as it says which is which."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, title, linkedin_url, connected_on FROM people "
            "WHERE contact_id = %s AND is_linkedin_contact AND deleted_at IS NULL ORDER BY name",
            (contact_id,),
        )
        linked = [serialize_row(dict(row)) for row in cur.fetchall()]
        cur.execute(
            "SELECT id, name, city FROM contacts WHERE id = %s AND deleted_at IS NULL",
            (contact_id,),
        )
        organization = cur.fetchone()
        possible: list[dict] = []
        if organization:
            cur.execute(
                "SELECT id, name, title, linkedin_url, connected_on, company_raw FROM people "
                "WHERE is_linkedin_contact AND contact_id IS NULL AND deleted_at IS NULL "
                "AND COALESCE(company_raw, '') <> '' "
                "AND NOT EXISTS (SELECT 1 FROM person_match_rejections r "
                "                WHERE r.person_id = people.id AND r.contact_id = %s) "
                "ORDER BY name",
                (contact_id,),
            )
            index = OrgIndex([dict(organization)])
            possible = [
                serialize_row(dict(row)) for row in cur.fetchall()
                if index.match(row["company_raw"])
            ]
    return {"linked": linked, "possible": possible}


def get_company_promotion_plan() -> CompanyPlan:
    """Read-only preview of promoting the employers of unlinked LinkedIn people
    to organizations. Writes nothing."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, company_raw FROM people "
            "WHERE is_linkedin_contact AND contact_id IS NULL AND deleted_at IS NULL"
        )
        people = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT id, name, city, source, company_key FROM contacts WHERE deleted_at IS NULL"
        )
        organizations = [dict(row) for row in cur.fetchall()]
    return plan_company_promotion(people, organizations)

