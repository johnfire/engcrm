"""
People (individual humans) database operations. Split out of db.py to keep that
file under the 600-line limit. A person is optionally linked to their company
contact via people.contact_id — e.g. the individual on a scanned business card.
"""
import logging

from gcrm.db.connection import db, serialize_row
from gcrm.geo import distance_km_sql
from gcrm.linkedin import normalize_linkedin_url
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.search import geocode
from gcrm.workspace_context import get_workspace_id

logger = logging.getLogger(__name__)


def _refresh_met_at(cur, person_id: int, met_at: str) -> int:
    """
    A re-scan carries a freshly typed met_at, so write it to the row we deduped
    onto — otherwise the new place is silently dropped. Returns person_id so the
    dedup branches can `return _refresh_met_at(...)` directly.

    An empty met_at is a no-op: re-saving a card without typing a place must not
    erase the place already recorded.
    """
    if not met_at:
        return person_id
    cur.execute(
        "UPDATE people SET met_at = %s, updated_at = NOW() WHERE id = %s",
        (met_at, person_id),
    )
    logger.info("save_person: updated met_at on existing person id=%d", person_id)
    return person_id


def find_existing_person(cur, name: str, email: str, contact_id: int | None) -> int | None:
    """The id of the person a new one would duplicate, or None. Same email (any
    case) wins; otherwise the same name at the same company. A NULL company
    matches another NULL (IS NOT DISTINCT FROM)."""
    if email:
        cur.execute("SELECT id FROM people WHERE lower(email) = lower(%s)", (email,))
        row = cur.fetchone()
        if row:
            return row["id"]
    cur.execute(
        "SELECT id FROM people WHERE lower(name) = lower(%s) "
        "AND contact_id IS NOT DISTINCT FROM %s",
        (name, contact_id),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def save_person(
    name: str,
    *,
    title: str = "",
    email: str = "",
    phone: str = "",
    website: str = "",
    city: str = "",
    country: str = "DE",
    relationship: str = "",
    notes: str = "",
    met_at: str = "",
    contact_id: int | None = None,
    source: str = "",
) -> int:
    """
    Insert a person, optionally linked to their company contact. Returns the new
    person's id, or the id of an existing match — dedup by email, else by
    (name, contact_id). Never returns 0, so the caller always gets a usable id.

    On a dedup hit the existing row is left as-is except for `met_at`, which a
    re-scan is allowed to update (a person can be met somewhere new). Every
    other field still belongs to whoever created the row first.

    A new row is geocoded from `city`/`country` (via Nominatim) so distance-
    from-home can be shown and sorted on — best-effort, city-level accuracy;
    failures leave latitude/longitude NULL rather than blocking the save.
    """
    with db() as conn:
        cur = conn.cursor()
        existing_id = find_existing_person(cur, name, email, contact_id)
        if existing_id:
            logger.debug("save_person: duplicate — %s (%s, contact_id=%s)", name, email, contact_id)
            return _refresh_met_at(cur, existing_id, met_at)

        latitude = longitude = None
        if city:
            coords = geocode(city, country)
            if coords:
                latitude, longitude = coords

        cur.execute(
            """
            INSERT INTO people
                (name, title, email, phone, website, city, country, relationship,
                 notes, met_at, contact_id, source, latitude, longitude, workspace_id)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default'))
            )
            RETURNING id
            """,
            (name, title or None, email or None, phone or None, website or None,
             city or None, country or None, relationship or None, notes or None,
             met_at or None, contact_id, source or None, latitude, longitude,
             get_workspace_id()),
        )
        person_id = cur.fetchone()["id"]
        logger.info("save_person: created id=%d  %s (contact_id=%s)", person_id, name, contact_id)
        return person_id


# Whitelisted so the UPDATE below builds its column list from constants only —
# never from submitted form keys. Deliberately excludes contact_id (the company
# link is a relation, not a text field) and source/created_at (provenance).
EDITABLE_COLUMNS = (
    "name", "title", "email", "phone", "website",
    "city", "country", "relationship", "notes", "met_at", "linkedin_url",
)


BOOLEAN_COLUMNS = ("is_linkedin_contact", "retention_hold")


def update_person(person_id: int, values: dict) -> bool:
    """
    Write the editable fields of one person. Only EDITABLE_COLUMNS keys present
    in `values` are written; blank strings become NULL. Returns False when the
    person does not exist, so the caller can 404 rather than silently no-op.

    `is_linkedin_contact` and `retention_hold` are the non-text fields: written as
    booleans when present. `pipeline_stage` is one of PIPELINE_STAGES (blank clears
    it) and raises ValueError otherwise. A non-blank `linkedin_url` is stored in its canonical form, and
    raises ValueError when it is not a linkedin.com link.
    """
    updates = {
        column: ((values.get(column) or "").strip() or None)
        for column in EDITABLE_COLUMNS
        if column in values
    }
    if updates.get("linkedin_url"):
        canonical = normalize_linkedin_url(updates["linkedin_url"])
        if canonical is None:
            raise ValueError("linkedin_url must be a linkedin.com link")
        updates["linkedin_url"] = canonical
    for column in BOOLEAN_COLUMNS:
        if column in values:
            updates[column] = bool(values[column])
    if "pipeline_stage" in values:
        stage = (values.get("pipeline_stage") or "").strip() or None
        if stage is not None and stage not in PIPELINE_STAGES:
            raise ValueError(f"unknown pipeline stage: {stage!r}")
        updates["pipeline_stage"] = stage
    if not updates:
        return False

    assignments = ", ".join(f"{column} = %s" for column in updates)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE people SET {assignments}, updated_at = NOW() WHERE id = %s",
            list(updates.values()) + [person_id],
        )
        if cur.rowcount == 0:
            logger.warning("update_person: no person with id=%s", person_id)
            return False
    logger.info("update_person: updated id=%d (%s)", person_id, ", ".join(updates))
    return True


_DISTANCE_KM_SQL = distance_km_sql(
    "COALESCE(person.latitude, company.latitude)",
    "COALESCE(person.longitude, company.longitude)",
)

_SELECT_WITH_COMPANY = (
    "SELECT person.*, company.name AS company, "
    "company.preferred_language AS company_language, "
    "company.pipeline_stage AS company_pipeline_stage, "
    "company_priority.priority AS company_personal_priority, "
    "company_opportunity.opportunity_score AS company_opportunity_score, "
    "person_priority.priority AS value_rating, "
    "(SELECT MAX(pi.occurred_at) FROM people_interactions pi "
    " WHERE pi.person_id = person.id AND pi.deleted_at IS NULL) AS last_contact, "
    f"({_DISTANCE_KM_SQL}) AS distance_km "
    "FROM people person "
    "LEFT JOIN contacts company ON company.id = person.contact_id "
    "LEFT JOIN ai_analysis company_opportunity "
    "ON company_opportunity.contact_id = company.id "
    "AND company_opportunity.analysis_kind = 'opportunity' "
    "AND company_opportunity.deleted_at IS NULL "
)

# Whitelisted so `sort` can be trusted straight into an f-string ORDER BY below.
# last_name strips everything up to the final space in the full name — there's
# no dedicated last-name column, `name` is stored as one free-text string.
# The three rating columns are only meaningful once _rating_joins/the
# opportunity join are in the query, which get_people/get_person always add.
SORT_COLUMNS = {
    "created_at":       "person.created_at",
    "name":             "lower(person.name)",
    "last_name":        r"lower(regexp_replace(trim(person.name), '.*\s', ''))",
    "company":          "lower(company.name)",
    "city":             "lower(person.city)",
    "met_at":           "lower(person.met_at)",
    "opportunity_score": "company_opportunity.opportunity_score",
    "company_priority": "company_priority.priority",
    "value_rating":     "person_priority.priority",
    "distance":         "distance_km",
    "connected_on":     "person.connected_on",
}

# `linkedin` filter values -> WHERE fragment. "unlinked" is the review queue:
# connections not yet tied to one of our organizations.
_LINKEDIN_FILTERS = {
    "1":        "person.is_linkedin_contact",
    "unlinked": "person.is_linkedin_contact AND person.contact_id IS NULL",
}


def _rating_joins(user_id: int | None) -> tuple[str, list]:
    """The two private per-user rating joins (company priority, person value
    rating), placed right after the FROM/company JOIN in _SELECT_WITH_COMPANY.
    Without a signed-in user_id both are unconditionally FALSE so the columns
    come back NULL rather than leaking another user's ratings."""
    if user_id is None:
        return (
            "LEFT JOIN contact_user_priorities company_priority ON FALSE "
            "LEFT JOIN person_user_priorities person_priority ON FALSE ",
            [],
        )
    return (
        "LEFT JOIN contact_user_priorities company_priority "
        "ON company_priority.contact_id = company.id AND company_priority.user_id = %s "
        "LEFT JOIN person_user_priorities person_priority "
        "ON person_priority.person_id = person.id AND person_priority.user_id = %s ",
        [user_id, user_id],
    )


_RATING_VALUES = {"1", "2", "3", "4", "5"}


def _rating_filter(conditions: list, params: list, column: str, value: str) -> None:
    """Append a `column = n` / `column IS NULL` condition for one rating filter
    (company_priority or value_rating), in place. A blank value is "any" and
    adds nothing."""
    if value in _RATING_VALUES:
        conditions.append(f"{column} = %s")
        params.append(int(value))
    elif value == "unrated":
        conditions.append(f"{column} IS NULL")


def get_people(
    search: str = "",
    sort: str = "created_at",
    dir: str = "desc",
    user_id: int | None = None,
    company_priority: str = "",
    value_rating: str = "",
    linkedin: str = "",
    stage: str = "",
) -> list[dict]:
    """All people, optionally filtered by name/email/city text search and/or
    company_priority / value_rating ("1".."5", "unrated", or "" for any —
    only meaningful when user_id is given, since both are private per-user)
    and/or `linkedin` ("1" = LinkedIn connections, "unlinked" = connections not
    yet tied to an organization, "" = everyone), and/or `stage` (a pipeline
    stage, "none" = no stage set, "" = any),
    sorted by `sort` (created_at|name|last_name|company|city|met_at|
    opportunity_score|company_priority|value_rating|distance|connected_on; default newest-added-first).
    Each row is annotated with its linked company's name, pipeline stage,
    opportunity score, most recent logged interaction date, and (when user_id
    is given) that user's private company-priority and person-value ratings."""
    sort_col = SORT_COLUMNS.get(sort, SORT_COLUMNS["created_at"])
    sort_dir = "DESC" if dir == "desc" else "ASC"
    rating_joins, rating_params = _rating_joins(user_id)
    select = _SELECT_WITH_COMPANY + rating_joins

    conditions = []
    params = list(rating_params)
    if search:
        like = f"%{search}%"
        conditions.append("(person.name ILIKE %s OR person.email ILIKE %s OR person.city ILIKE %s)")
        params += [like, like, like]
    _rating_filter(conditions, params, "company_priority.priority", company_priority)
    _rating_filter(conditions, params, "person_priority.priority", value_rating)
    if linkedin in _LINKEDIN_FILTERS:
        conditions.append(_LINKEDIN_FILTERS[linkedin])
    if stage == "none":
        conditions.append("person.pipeline_stage IS NULL")
    elif stage in PIPELINE_STAGES:
        conditions.append("person.pipeline_stage = %s")
        params.append(stage)
    where = f"WHERE {' AND '.join(conditions)} " if conditions else ""

    # NULLS LAST regardless of direction — an unrated/unlinked person should
    # never jump to the top of a descending sort just for lacking a value.
    order_by = f"ORDER BY {sort_col} {sort_dir} NULLS LAST"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(select + where + order_by, params)
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def get_person(person_id: int, user_id: int | None = None) -> dict | None:
    """One person with their linked company's name, pipeline stage, opportunity
    score, and (when user_id is given) that user's private ratings — or None if
    not found."""
    rating_joins, rating_params = _rating_joins(user_id)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            _SELECT_WITH_COMPANY + rating_joins + "WHERE person.id = %s",
            rating_params + [person_id],
        )
        row = cur.fetchone()
        return serialize_row(dict(row)) if row else None


def get_person_value_rating(user_id: int, workspace_id: int, person_id: int) -> int | None:
    """Return one user's private value-as-a-contact rating for one person."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT priority
            FROM person_user_priorities
            WHERE user_id = %s AND workspace_id = %s AND person_id = %s
            """,
            (user_id, workspace_id, person_id),
        )
        row = cur.fetchone()
        return row["priority"] if row else None


def set_person_value_rating(
    user_id: int, workspace_id: int, person_id: int, rating: int | None,
) -> tuple[bool, int | None]:
    """Set or clear a user's private value-as-a-contact rating for one person,
    returning (person_found, stored_rating)."""
    if rating is not None and rating not in range(1, 6):
        raise ValueError("Contact value rating must be between 1 and 5")

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM people p
            JOIN users u
              ON u.id = %s
             AND u.workspace_id = %s
             AND u.is_active = TRUE
            WHERE p.id = %s
              AND p.workspace_id = u.workspace_id
            """,
            (user_id, workspace_id, person_id),
        )
        if cur.fetchone() is None:
            return False, None

        if rating is None:
            cur.execute(
                "DELETE FROM person_user_priorities "
                "WHERE user_id = %s AND workspace_id = %s AND person_id = %s",
                (user_id, workspace_id, person_id),
            )
            return True, None

        cur.execute(
            """
            INSERT INTO person_user_priorities (workspace_id, user_id, person_id, priority)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, person_id)
            DO UPDATE SET
                priority = EXCLUDED.priority,
                workspace_id = EXCLUDED.workspace_id,
                updated_at = NOW()
            RETURNING priority
            """,
            (workspace_id, user_id, person_id, rating),
        )
        return True, cur.fetchone()["priority"]


def search_organizations(query: str, limit: int = 20) -> list[dict]:
    """Organizations whose name or city contains `query`, for linking a person to
    one by hand. A blank query returns nothing rather than the whole table."""
    query = (query or "").strip()
    if not query:
        return []
    like = f"%{query}%"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, city, status FROM contacts "
            "WHERE deleted_at IS NULL AND (name ILIKE %s OR city ILIKE %s) "
            "ORDER BY lower(name) LIMIT %s",
            (like, like, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def set_person_organization(person_id: int, contact_id: int | None) -> bool:
    """Link a person to an organization, or unlink them with `contact_id=None`.
    Returns False when the person (or the organization) does not exist.

    Unlinking remembers the organization as rejected for that person, so the
    LinkedIn match review does not offer the same pairing again; linking clears
    any earlier rejection of the pair."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT contact_id FROM people WHERE id = %s", (person_id,))
        row = cur.fetchone()
        if row is None:
            return False
        if contact_id is None:
            previous = row["contact_id"]
            cur.execute("UPDATE people SET contact_id = NULL WHERE id = %s", (person_id,))
            if previous is not None:
                cur.execute(
                    "INSERT INTO person_match_rejections (person_id, contact_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (person_id, previous),
                )
            return True
        cur.execute(
            "UPDATE people SET contact_id = %s WHERE id = %s "
            "AND EXISTS (SELECT 1 FROM contacts WHERE id = %s AND deleted_at IS NULL)",
            (contact_id, person_id, contact_id),
        )
        if cur.rowcount == 0:
            return False
        cur.execute(
            "DELETE FROM person_match_rejections WHERE person_id = %s AND contact_id = %s",
            (person_id, contact_id),
        )
        return True
