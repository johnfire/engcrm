"""Workspace-scoped businesses with contacted people grouped underneath."""
from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_contact_feed_query import CONTACT_FEED_SQL

PAGE_SIZE = 50
KINDS = ("", "person", "organization")
SORT_ORDERS = {
    "last_contact": "last_contact DESC NULLS LAST, kind, id DESC",
    "newest": "last_contact DESC NULLS LAST, kind, id DESC",  # Older mobile clients use this sort key.
    "name": "lower(name), kind, id",
}


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
            f"{column} ILIKE %s ESCAPE '!'" for column in ("name", "description", "company", "city", "email", "phone", "searchable_people")
        ) + ")")
        parameters.extend([pattern] * 7)
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
