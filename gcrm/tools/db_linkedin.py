"""
LinkedIn connection database operations: importing Connections.csv rows as
people, suggesting which of our organizations each connection works at, and
answering "who do I know at this organization?".

Every per-row write runs inside its own SAVEPOINT, so one bad row is counted
and skipped instead of aborting the whole import.
"""
import logging
import re
from contextlib import contextmanager

from psycopg2.extras import Json

from gcrm.db.connection import db, serialize_row
from gcrm.linkedin import (
    CompanyPlan,
    OrgIndex,
    linkedin_url_hash,
    normalize_company,
    plan_company_promotion,
)
from gcrm.organization_state import coerce_stage, coerce_status
from gcrm.tools.company_places import PlacesError, decide_city, lookup_places
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_company_web import apply_reading
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


def _company_change(cur, person_id: int, row: dict) -> str:
    """Compare the employer this export shows with the one we hold for the
    person, and record a difference for a human instead of acting on it.
    Returns 'flagged' when a change is (still) pending, else ''.

    Only a real difference counts: both sides must be actual companies, and the
    same company spelled differently ("Acme GmbH" / "ACME") is not a move. A
    change the user already said is not a move ("keep") is not flagged again."""
    cur.execute(
        "SELECT company_raw, ignored_company_key, pending_company_raw FROM people WHERE id = %s",
        (person_id,),
    )
    known = cur.fetchone()
    if not known:
        return ""
    seen, held = normalize_company(row["company"]), normalize_company(known["company_raw"])
    if not seen or not held:
        return ""  # a blank / "self-employed" side tells us nothing about a move
    if seen == held:
        if known["pending_company_raw"]:  # they are back at the stored employer
            cur.execute(
                "UPDATE people SET pending_company_raw = NULL, pending_title = NULL, "
                "pending_seen_at = NULL WHERE id = %s", (person_id,))
        return ""
    if seen == (known["ignored_company_key"] or ""):
        return ""
    cur.execute(
        """
        UPDATE people SET
            pending_seen_at = CASE WHEN pending_company_raw IS DISTINCT FROM %s
                                   THEN NOW() ELSE pending_seen_at END,
            pending_company_raw = %s,
            pending_title = %s
        WHERE id = %s
        """,
        (row["company"], row["company"], row["title"] or None, person_id),
    )
    return "flagged"


def _upsert_connection(cur, row: dict) -> tuple[str, bool]:
    """Write one connection. Existing people are marked and have only their
    blank fields filled — nothing you typed is overwritten; a different employer
    is flagged for review, not applied. Returns ('created' | 'updated',
    company_change_flagged)."""
    person_id = _find_existing_person(cur, row)
    if person_id is not None:
        flagged = _company_change(cur, person_id, row) == "flagged"
        cur.execute(
            """
            UPDATE people SET
                is_linkedin_contact = TRUE,
                linkedin_url = COALESCE(NULLIF(linkedin_url, ''), %s),
                connected_on = COALESCE(connected_on, %s),
                company_raw  = COALESCE(NULLIF(company_raw, ''), %s),
                title        = COALESCE(NULLIF(title, ''), %s),
                email        = COALESCE(NULLIF(email, ''), %s),
                pipeline_stage = COALESCE(pipeline_stage, 'candidate'),
                updated_at   = NOW()
            WHERE id = %s
            """,
            (row["linkedin_url"], row["connected_on"], row["company"] or None,
             row["title"] or None, row["email"] or None, person_id),
        )
        return "updated", flagged
    cur.execute(
        """
        INSERT INTO people
            (name, title, email, country, source, is_linkedin_contact,
             linkedin_url, connected_on, company_raw, pipeline_stage, workspace_id)
        VALUES (
            %s, %s, %s, NULL, %s, TRUE, %s, %s, %s, 'candidate',
            COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default'))
        )
        """,
        (row["name"], row["title"] or None, row["email"] or None, IMPORT_SOURCE,
         row["linkedin_url"], row["connected_on"], row["company"] or None,
         get_workspace_id()),
    )
    return "created", False


def import_connections(rows: list[dict]) -> dict:
    """Import parsed Connections.csv rows. Idempotent: re-importing a fresh
    export marks/updates the same people instead of duplicating them. Returns
    counts — created, updated, failed, suppressed (skipped because deleted earlier),
    company_changed (an existing person whose employer differs from the one we hold)."""
    counts = {"created": 0, "updated": 0, "failed": 0, "suppressed": 0, "company_changed": 0}
    with db() as conn:
        cur = conn.cursor()
        for row in rows:
            try:
                with _savepoint(cur):
                    if _is_suppressed(cur, row):
                        counts["suppressed"] += 1
                        continue
                    outcome, flagged = _upsert_connection(cur, row)
                    counts[outcome] += 1
                    counts["company_changed"] += 1 if flagged else 0
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


ORGANIZATION_SOURCE = "linkedin"


def _link_people(cur, contact_id: int, people_ids: list[int]) -> int:
    """Attach still-unlinked LinkedIn people to an organization, except those who
    were once explicitly unlinked from it (their rejection stands)."""
    cur.execute(
        "UPDATE people SET contact_id = %s, updated_at = NOW() "
        "WHERE id = ANY(%s) AND is_linkedin_contact AND contact_id IS NULL "
        "AND deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM person_match_rejections r "
        "                WHERE r.person_id = people.id AND r.contact_id = %s)",
        (contact_id, people_ids, contact_id),
    )
    return cur.rowcount


def _create_company_organization(cur, group: dict) -> tuple[int, bool]:
    """Insert (or find, if a concurrent run just made it) the organization for
    one employer. The partial unique index on (workspace_id, company_key) is the
    guard, so re-running can never produce a second one."""
    cur.execute(
        """
        INSERT INTO contacts
            (name, pipeline_stage, status, source, company_key, city_status, workspace_id)
        VALUES (%s, %s, %s, %s, %s, 'needs_review',
                COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default')))
        ON CONFLICT (workspace_id, company_key)
            WHERE source = 'linkedin' AND company_key IS NOT NULL AND deleted_at IS NULL
        DO NOTHING
        RETURNING id
        """,
        (group["name"], coerce_stage("candidate"), coerce_status("none"),
         ORGANIZATION_SOURCE, group["key"], get_workspace_id()),
    )
    created = cur.fetchone()
    if created:
        return created["id"], True
    cur.execute(
        "SELECT id FROM contacts WHERE source = 'linkedin' AND company_key = %s "
        "AND deleted_at IS NULL ORDER BY id LIMIT 1",
        (group["key"],),
    )
    return cur.fetchone()["id"], False


def apply_company_plan(plan: CompanyPlan, limit: int | None = None) -> dict:
    """Carry out a promotion plan. Each employer is its own SAVEPOINT, so one bad
    row is counted and skipped. `limit` caps how many organizations are
    *created* (linking existing ones is free). Returns counts — created, linked,
    people_linked, failed, ambiguous_skipped."""
    counts = {"created": 0, "linked": 0, "people_linked": 0, "failed": 0,
              "ambiguous_skipped": len(plan.ambiguous)}
    with db() as conn:
        cur = conn.cursor()
        for group in plan.link:
            try:
                with _savepoint(cur):
                    linked = _link_people(cur, group["contact_id"], group["people_ids"])
                    counts["people_linked"] += linked
                    counts["linked"] += 1 if linked else 0
            except Exception:
                counts["failed"] += 1
                logger.warning("linkedin companies: link failed for %r", group["name"], exc_info=True)
        for group in plan.create:
            if limit is not None and counts["created"] >= limit:
                break
            try:
                with _savepoint(cur):
                    contact_id, is_new = _create_company_organization(cur, group)
                    counts["people_linked"] += _link_people(cur, contact_id, group["people_ids"])
                    counts["created"] += 1 if is_new else 0
            except Exception:
                counts["failed"] += 1
                logger.warning("linkedin companies: create failed for %r", group["name"], exc_info=True)
    logger.info("linkedin companies: %s", counts)
    if counts["created"] or counts["people_linked"]:  # a no-op rerun leaves no audit noise
        log_audit(None, None, "linkedin.companies_promoted", None,
                  f"created={counts['created']} people_linked={counts['people_linked']}")
    return counts


def promote_linkedin_companies(limit: int | None = None) -> dict:
    """Plan and apply in one go; see apply_company_plan."""
    return apply_company_plan(get_company_promotion_plan(), limit=limit)


# --- City resolution ---------------------------------------------------------

MAX_CONSECUTIVE_LOOKUP_ERRORS = 5
_NEEDS_CITY = (
    "c.source = 'linkedin' AND c.city_status = 'needs_review' AND c.deleted_at IS NULL "
    "AND c.company_key IS NOT NULL"
)


def count_city_work() -> dict:
    """What a city-resolution run would do: `to_lookup` companies that have never
    been looked up (each one billed request), `cached_ready` that already have an
    accepted city waiting to be applied."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(DISTINCT c.company_key) AS n FROM contacts c WHERE {_NEEDS_CITY} "
            "AND NOT EXISTS (SELECT 1 FROM company_city_lookups l WHERE l.company_key = c.company_key)"
        )
        to_lookup = cur.fetchone()["n"]
        cur.execute(
            f"SELECT COUNT(DISTINCT c.company_key) AS n FROM contacts c WHERE {_NEEDS_CITY} "
            "AND EXISTS (SELECT 1 FROM company_city_lookups l "
            "            WHERE l.company_key = c.company_key AND l.outcome = 'resolved')"
        )
        return {"to_lookup": to_lookup, "cached_ready": cur.fetchone()["n"]}


def apply_cached_cities() -> int:
    """Fill the city of organizations still waiting for one from lookups we
    already paid for. Never overwrites a city that is set. Returns rows updated."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE contacts c
               SET city = l.city, country = l.country, city_status = 'resolved', updated_at = NOW()
              FROM company_city_lookups l
             WHERE l.company_key = c.company_key AND l.outcome = 'resolved'
               AND {_NEEDS_CITY} AND COALESCE(c.city, '') = ''
            """
        )
        return cur.rowcount


def resolve_company_cities(limit: int = 200, lookup=lookup_places) -> dict:
    """Look up the city of LinkedIn-created organizations that have none, most
    connections first, at most `limit` billed lookups. Every outcome is cached.

    Anti-fragile: one failed lookup is counted and skipped; a failure that would
    repeat for every company (bad key, quota spent) or five in a row stops the run
    and keeps what was done. Returns counts — applied_cached, looked_up, resolved,
    ambiguous, not_found, errors, stopped (reason or "")."""
    counts = {"applied_cached": apply_cached_cities(), "looked_up": 0, "resolved": 0,
              "ambiguous": 0, "not_found": 0, "errors": 0, "stopped": ""}
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT DISTINCT ON (c.company_key) c.company_key, c.name,
                   (SELECT COUNT(*) FROM people p
                     WHERE p.contact_id = c.id AND p.deleted_at IS NULL) AS people
              FROM contacts c
             WHERE {_NEEDS_CITY}
               AND NOT EXISTS (SELECT 1 FROM company_city_lookups l
                                WHERE l.company_key = c.company_key)
             ORDER BY c.company_key, people DESC
            """
        )
        todo = sorted((dict(r) for r in cur.fetchall()), key=lambda r: (-r["people"], r["name"]))[:limit]

    consecutive_errors = 0
    for item in todo:
        try:
            places = lookup(item["name"])
        except PlacesError as error:
            counts["errors"] += 1
            consecutive_errors += 1
            logger.warning("city lookup failed for %r: %s", item["name"], error)
            if error.fatal or consecutive_errors >= MAX_CONSECUTIVE_LOOKUP_ERRORS:
                counts["stopped"] = str(error)
                break
            continue
        consecutive_errors = 0
        decision = decide_city(item["company_key"], places)
        try:
            with db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO company_city_lookups
                        (company_key, outcome, city, country, place_id, candidates)
                    VALUES (%s, %s, NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), %s)
                    ON CONFLICT (company_key) DO UPDATE SET
                        outcome = EXCLUDED.outcome, city = EXCLUDED.city,
                        country = EXCLUDED.country, place_id = EXCLUDED.place_id,
                        candidates = EXCLUDED.candidates, looked_up_at = NOW()
                    """,
                    (item["company_key"], decision.outcome, decision.city, decision.country,
                     decision.place_id, Json(decision.candidates)),
                )
                if decision.outcome == "resolved":
                    cur.execute(
                        "UPDATE contacts c SET city = %s, country = %s, city_status = 'resolved', "
                        f"updated_at = NOW() WHERE c.company_key = %s AND {_NEEDS_CITY} "
                        "AND COALESCE(c.city, '') = ''",
                        (decision.city, decision.country, item["company_key"]),
                    )
        except Exception:
            counts["errors"] += 1
            logger.warning("city result not saved for %r", item["name"], exc_info=True)
            continue
        counts["looked_up"] += 1
        counts[decision.outcome] += 1
    logger.info("linkedin cities: %s", counts)
    if counts["looked_up"] or counts["applied_cached"]:
        log_audit(None, None, "linkedin.cities_resolved", None,
                  f"looked_up={counts['looked_up']} resolved={counts['resolved']}")
    return counts


CITY_LOOKUP_LOCK_KEY = 7_340_011  # arbitrary, app-wide constant for pg advisory locks
WEB_LOOKUP_MAX = 50  # most billed lookups one browser click may start


def run_city_lookup(limit: int) -> dict:
    """resolve_company_cities for the browser: the limit is clamped to
    1..WEB_LOOKUP_MAX, and a Postgres advisory lock lets only one run go at a
    time, so a double click or two tabs cannot bill the same companies twice.
    Returns resolve_company_cities' counts; `stopped` explains a refused run."""
    limit = max(1, min(int(limit), WEB_LOOKUP_MAX))
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s) AS got", (CITY_LOOKUP_LOCK_KEY,))
        if not cur.fetchone()["got"]:
            return {"applied_cached": 0, "looked_up": 0, "resolved": 0, "ambiguous": 0,
                    "not_found": 0, "errors": 0, "stopped": "another lookup is already running"}
        try:
            return resolve_company_cities(limit=limit)
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (CITY_LOOKUP_LOCK_KEY,))


# --- City review queue -------------------------------------------------------

CITY_QUEUE_PAGE_SIZE = 100
_COUNTRY_CODE = re.compile(r"^[A-Za-z]{2}$")


def get_city_review_queue(page: int = 1) -> dict:
    """Organizations created from LinkedIn that still need a city, the ones with
    the most connections first, each with the people you know there and, when a
    lookup was made, what it found. Returns {total, rows}."""
    offset = (max(page, 1) - 1) * CITY_QUEUE_PAGE_SIZE
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS n FROM contacts c WHERE {_NEEDS_CITY}")
        total = cur.fetchone()["n"]
        cur.execute(
            f"""
            SELECT c.id, c.name, l.outcome AS lookup_outcome, l.candidates,
                   wl.outcome AS web_outcome, wl.website AS web_website, wl.street AS web_street,
                   wl.postal_code AS web_postal_code, wl.city AS web_city,
                   wl.country AS web_country, wl.source_url AS web_source, wl.reason AS web_reason,
                   COUNT(p.id) AS people_count,
                   COALESCE(json_agg(json_build_object(
                       'id', p.id, 'name', p.name, 'title', p.title)
                       ORDER BY p.name) FILTER (WHERE p.id IS NOT NULL), '[]'::json) AS people
              FROM contacts c
              LEFT JOIN people p ON p.contact_id = c.id AND p.deleted_at IS NULL
                                AND p.is_linkedin_contact
              LEFT JOIN company_city_lookups l ON l.company_key = c.company_key
              LEFT JOIN company_web_lookups wl ON wl.company_key = c.company_key
             WHERE {_NEEDS_CITY}
             GROUP BY c.id, l.company_key, wl.company_key
             ORDER BY people_count DESC, lower(c.name), c.id
             LIMIT %s OFFSET %s
            """,
            (CITY_QUEUE_PAGE_SIZE, offset),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        # Places offered these; the distinct cities become one-click choices.
        seen, choices = set(), []
        for candidate in row.pop("candidates") or []:
            key = (candidate.get("city") or "", candidate.get("country") or "")
            if key[0] and key not in seen:
                seen.add(key)
                choices.append({"city": key[0], "country": key[1]})
        row["choices"] = choices
    return {"total": total, "rows": rows}


def apply_city_decisions(decisions: list[dict]) -> dict:
    """Apply the review page. Each decision is {contact_id, city, country,
    dismiss}: a city (and optional 2-letter country) is saved as entered by
    hand; `dismiss` stops asking about that organization. Only organizations
    still waiting are touched, so a stale form cannot overwrite a newer answer.
    A decision with `accept` takes the website and address that were read from the
    company's own pages (the country may be typed if the page did not give one).
    Returns counts — saved, dismissed, failed."""
    counts = {"saved": 0, "dismissed": 0, "failed": 0}
    with db() as conn:
        cur = conn.cursor()
        for decision in decisions:
            try:
                with _savepoint(cur):
                    if decision.get("dismiss"):
                        cur.execute(
                            f"UPDATE contacts c SET city_status = 'dismissed', updated_at = NOW() "
                            f"WHERE c.id = %s AND {_NEEDS_CITY}",
                            (decision["contact_id"],),
                        )
                        counts["dismissed"] += cur.rowcount
                        continue
                    city = (decision.get("city") or "").strip()[:100]
                    country = (decision.get("country") or "").strip()
                    if not city and decision.get("accept"):
                        counts["saved"] += _accept_reading(cur, decision["contact_id"], country)
                        continue
                    if not city:
                        continue
                    if country and not _COUNTRY_CODE.match(country):
                        raise ValueError(f"country must be a 2-letter code: {country!r}")
                    cur.execute(
                        f"UPDATE contacts c SET city = %s, country = COALESCE(%s, c.country), "
                        f"city_status = 'manual', updated_at = NOW() "
                        f"WHERE c.id = %s AND {_NEEDS_CITY}",
                        (city, country.upper() or None, decision["contact_id"]),
                    )
                    counts["saved"] += cur.rowcount
            except Exception:
                counts["failed"] += 1
                logger.warning("city decision failed %r", decision, exc_info=True)
    logger.info("linkedin city decisions: %s", counts)
    return counts


# --- Reachable fits ----------------------------------------------------------

REACHABLE_PAGE_SIZE = 50


def get_reachable_fits(page: int = 1, workspace_id: int | None = None) -> dict:
    """Organizations that are a fit (stage suspect, status ready — scored a fit,
    not yet contacted) where you know someone on LinkedIn: the warm-intro work
    list, best fit first. Each carries the people you know there. Organizations
    that opted out are left off. Returns {total, rows}."""
    offset = (max(page, 1) - 1) * REACHABLE_PAGE_SIZE
    conditions = [
        "c.pipeline_stage = 'suspect'", "c.status = 'ready'",
        "c.deleted_at IS NULL", "c.do_not_contact = FALSE",
        "EXISTS (SELECT 1 FROM people k WHERE k.contact_id = c.id "
        "AND k.is_linkedin_contact AND k.deleted_at IS NULL)",
    ]
    params: list = []
    if workspace_id is not None:
        conditions.append("c.workspace_id = %s")
        params.append(workspace_id)
    where = " AND ".join(conditions)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS n FROM contacts c WHERE {where}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"""
            SELECT c.id, c.name, c.city, c.country, c.type, c.website, c.fit_score,
                   (SELECT COALESCE(json_agg(json_build_object(
                               'id', p.id, 'name', p.name, 'title', p.title,
                               'linkedin_url', p.linkedin_url, 'connected_on', p.connected_on)
                               ORDER BY p.name), '[]'::json)
                      FROM people p
                     WHERE p.contact_id = c.id AND p.is_linkedin_contact
                       AND p.deleted_at IS NULL) AS people
              FROM contacts c
             WHERE {where}
             ORDER BY c.fit_score DESC NULLS LAST, lower(c.name), c.id
             LIMIT %s OFFSET %s
            """,
            params + [REACHABLE_PAGE_SIZE, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"total": total, "rows": rows}


# --- Job-change review -------------------------------------------------------

JOB_CHANGE_PAGE_SIZE = 100


def get_company_changes(page: int = 1) -> dict:
    """People a newer export shows at a different employer than we hold, oldest
    first, with the organization they are linked to now. Returns {total, rows}."""
    offset = (max(page, 1) - 1) * JOB_CHANGE_PAGE_SIZE
    where = "p.pending_company_raw IS NOT NULL AND p.deleted_at IS NULL AND p.is_linkedin_contact"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS n FROM people p WHERE {where}")
        total = cur.fetchone()["n"]
        cur.execute(
            f"""
            SELECT p.id, p.name, p.title, p.company_raw, p.pending_company_raw, p.pending_title,
                   p.pending_seen_at, p.contact_id, c.name AS organization
              FROM people p LEFT JOIN contacts c ON c.id = p.contact_id
             WHERE {where}
             ORDER BY p.pending_seen_at, p.id
             LIMIT %s OFFSET %s
            """,
            (JOB_CHANGE_PAGE_SIZE, offset),
        )
        return {"total": total, "rows": [serialize_row(dict(r)) for r in cur.fetchall()]}


def apply_company_change_decisions(decisions: list[dict]) -> dict:
    """Apply the review page. Each decision is {person_id, action, seen}:

    move  the person changed jobs — they take the new company and position and
          are unlinked from the old organization, ready to be matched to (or
          create) the new one the next time companies are promoted
    keep  not a real move — the old employer stays, and this change is never
          flagged again

    `seen` is the pending company the form showed; a decision only applies if it
    is still pending, so a stale form cannot act on a newer change. Returns
    counts — moved, kept, failed."""
    counts = {"moved": 0, "kept": 0, "failed": 0}
    with db() as conn:
        cur = conn.cursor()
        for decision in decisions:
            try:
                with _savepoint(cur):
                    if decision["action"] == "move":
                        cur.execute(
                            """
                            UPDATE people SET
                                company_raw = pending_company_raw,
                                title = COALESCE(NULLIF(pending_title, ''), title),
                                contact_id = NULL, ignored_company_key = NULL,
                                pending_company_raw = NULL, pending_title = NULL,
                                pending_seen_at = NULL, updated_at = NOW()
                            WHERE id = %s AND pending_company_raw = %s AND deleted_at IS NULL
                            """,
                            (decision["person_id"], decision["seen"]),
                        )
                        counts["moved"] += cur.rowcount
                    elif decision["action"] == "keep":
                        cur.execute(
                            """
                            UPDATE people SET
                                ignored_company_key = %s,
                                pending_company_raw = NULL, pending_title = NULL,
                                pending_seen_at = NULL, updated_at = NOW()
                            WHERE id = %s AND pending_company_raw = %s AND deleted_at IS NULL
                            """,
                            (normalize_company(decision["seen"]), decision["person_id"], decision["seen"]),
                        )
                        counts["kept"] += cur.rowcount
            except Exception:
                counts["failed"] += 1
                logger.warning("company change decision failed %r", decision, exc_info=True)
    logger.info("linkedin company changes: %s", counts)
    return counts


def _accept_reading(cur, contact_id: int, typed_country: str) -> int:
    """Use the website and address read from the company's own pages, as confirmed
    by a human. Only for an organization still waiting, and only a reading that
    includes a town; a country is needed from the page or from the person."""
    cur.execute(
        f"""
        SELECT c.company_key, w.website, w.street, w.postal_code, w.city, w.country, w.source_url
          FROM contacts c JOIN company_web_lookups w ON w.company_key = c.company_key
         WHERE c.id = %s AND {_NEEDS_CITY} AND w.city IS NOT NULL
        """,
        (contact_id,),
    )
    reading = cur.fetchone()
    if not reading:
        return 0
    country = (typed_country or reading["country"] or "").strip()
    if not _COUNTRY_CODE.match(country):
        raise ValueError("the reading has no country; type a 2-letter code")
    address = ", ".join(p for p in (reading["street"] or "",
                                    f"{reading['postal_code'] or ''} {reading['city']}".strip()) if p)
    return apply_reading(cur, reading["company_key"], reading["website"] or "", address,
                         reading["city"], country.upper(), reading["source_url"] or "", "manual")

