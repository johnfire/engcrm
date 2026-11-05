"""Storage for the people found by web search (gcrm.people_finder): which companies still
need a search, and saving what was found — onto an existing person where there is one."""
from gcrm.db.connection import db, serialize_row
from gcrm.linkedin import normalize_linkedin_url
from gcrm.sources import RESEARCH_AGENT
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_deals import organization_deal_join
from gcrm.tools.db_people import save_person


def get_organizations_needing_people(limit: int = 20, ids: list[int] | None = None) -> list[dict]:
    """Companies not yet searched for people: the given ones (a Gather run's, judged or
    not), or else the ones the scout rated ready, best fit first."""
    scope, params = ("c.id = ANY(%s)", [list(ids)]) if ids is not None else ("d.status = 'ready'", [])
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT c.*, d.pipeline_stage, d.status FROM contacts c" + organization_deal_join("c", "d")
            + f" WHERE {scope} AND c.deleted_at IS NULL AND c.people_searched_at IS NULL"
            " ORDER BY c.fit_score DESC NULLS LAST, c.created_at ASC LIMIT %s",
            (*params, limit),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def _person_with_profile(cur, linkedin_url: str | None) -> int | None:
    canonical = normalize_linkedin_url(linkedin_url)
    if not canonical:
        return None
    cur.execute("SELECT id, linkedin_url FROM people WHERE deleted_at IS NULL AND linkedin_url IS NOT NULL")
    return next((row["id"] for row in cur.fetchall() if normalize_linkedin_url(row["linkedin_url"]) == canonical), None)


def save_found_person(organization: dict, person: dict) -> dict:
    """Save one found person (or find the one they already are) and record their profiles.
    Returns {person_id, name, linkedin_url, xing_url, is_connection}."""
    with db() as conn:
        existing_id = _person_with_profile(conn.cursor(), person.get("linkedin_url"))
    source_note = f"Found via web search: {person['source_url']}" if person.get("source_url") else "Found via web search."
    person_id = existing_id or save_person(
        person["name"], source=RESEARCH_AGENT, title=person.get("role") or "",
        city=organization.get("city") or "", country=organization.get("country") or "DE",
        notes=source_note, contact_id=organization["id"],
    )
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE people SET linkedin_url = COALESCE(linkedin_url, %s), xing_url = COALESCE(xing_url, %s),
                   profile_searched_at = NOW(), updated_at = NOW()
               WHERE id = %s RETURNING id, name, linkedin_url, xing_url, is_linkedin_contact""",
            (person.get("linkedin_url"), person.get("xing_url"), person_id),
        )
        row = cur.fetchone()
    log_audit(None, None, "person.found_by_web_search", f"person:{person_id}",
              "profile" if row["linkedin_url"] or row["xing_url"] else "no_public_profile")
    return {"person_id": row["id"], "name": row["name"], "linkedin_url": row["linkedin_url"],
            "xing_url": row["xing_url"], "is_connection": row["is_linkedin_contact"]}


def mark_people_searched(contact_id: int) -> None:
    with db() as conn:
        conn.cursor().execute(
            "UPDATE contacts SET people_searched_at = NOW(), updated_at = NOW() WHERE id = %s", (contact_id,))
