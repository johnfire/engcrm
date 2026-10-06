"""One chronological, workspace-scoped list of people and organizations."""
from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_contact_dates import CONTACT_HISTORY_FILTER, contact_day_sql

PAGE_SIZE = 50
KINDS = ("", "person", "organization")
SORT_ORDERS = {
    "last_contact": "last_contact DESC NULLS LAST, kind, id DESC",
    "newest": "last_contact DESC NULLS LAST, kind, id DESC",  # Older mobile clients use this sort key.
    "name": "lower(name), kind, id",
}

CONTACT_FEED_SQL = f"""
WITH contact_feed AS (
    SELECT organization.id, 'organization' AS kind, organization.name,
           organization.type AS description, NULL::text AS company,
           organization.city, organization.email, organization.phone,
           organization.pipeline_stage, organization.created_at, organization.workspace_id,
           (SELECT MAX(interaction_date) FROM interactions
             WHERE contact_id=organization.id AND {CONTACT_HISTORY_FILTER}) AS last_contact
      FROM contacts organization WHERE organization.deleted_at IS NULL
    UNION ALL
    SELECT person.id, 'person' AS kind, person.name, person.title AS description,
           COALESCE(organization.name, person.company_raw) AS company,
           COALESCE(NULLIF(person.city, ''), organization.city) AS city,
           person.email, person.phone, person.pipeline_stage,
           person.created_at, person.workspace_id,
           (SELECT MAX({contact_day_sql("person", "occurred_at")}) FROM people_interactions
             WHERE person_id=person.id AND {CONTACT_HISTORY_FILTER}) AS last_contact
      FROM people person
      LEFT JOIN contacts organization ON organization.id=person.contact_id
           AND organization.deleted_at IS NULL AND organization.workspace_id=person.workspace_id
     WHERE person.deleted_at IS NULL
)
SELECT id, kind, name, description, company, city, email, phone, pipeline_stage, created_at, last_contact
FROM contact_feed
"""


def validate_feed_filters(kind: str, stage: str, sort: str) -> None:
    if kind not in KINDS:
        raise ValueError("Unknown contact type")
    if stage not in ("", "none", *PIPELINE_STAGES):
        raise ValueError("Unknown pipeline stage")
    if sort not in SORT_ORDERS:
        raise ValueError("Unknown contact sort")


def feed_predicates(search: str, kind: str, stage: str, workspace_id: int | None) -> tuple[str, list]:
    clauses, parameters = ["last_contact IS NOT NULL"], []
    if workspace_id is not None:
        clauses.append("workspace_id=%s")
        parameters.append(workspace_id)
    if kind:
        clauses.append("kind=%s")
        parameters.append(kind)
    if stage == "none":
        clauses.append("NULLIF(pipeline_stage, '') IS NULL")
    elif stage:
        clauses.append("pipeline_stage=%s")
        parameters.append(stage)
    for word in search.split()[:4]:
        pattern = "%" + word.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        clauses.append("(" + " OR ".join(
            f"{column} ILIKE %s ESCAPE '!'" for column in ("name", "description", "company", "city", "email", "phone")
        ) + ")")
        parameters.extend([pattern] * 6)
    return " AND ".join(clauses) or "TRUE", parameters


def get_contact_feed(*, search: str = "", kind: str = "", stage: str = "", sort: str = "last_contact",
                     page: int = 1, workspace_id: int | None = None, extra_row: bool = False) -> list[dict]:
    validate_feed_filters(kind, stage, sort)
    if page < 1:
        raise ValueError("Page must be positive")
    predicate, parameters = feed_predicates(search, kind, stage, workspace_id)
    query = CONTACT_FEED_SQL + f" WHERE {predicate} ORDER BY {SORT_ORDERS[sort]} LIMIT %s OFFSET %s"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(query, parameters + [PAGE_SIZE + int(extra_row), (page - 1) * PAGE_SIZE])
        return [serialize_row(dict(row)) for row in cursor.fetchall()]
