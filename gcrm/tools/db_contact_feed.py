"""Workspace-scoped businesses with contacted people grouped underneath."""
from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_contact_feed_query import contact_feed_sql
from gcrm.tools.db_deals import CONSULTING

PAGE_SIZE = 50
KINDS = ("", "person", "organization")
SORT_COLUMNS = {
    "last_contact": "last_contact",
    "newest": "last_contact",  # Older mobile clients use this sort key.
    "name": "lower(name)",
    "city": "lower(city)",
    "kind": "kind",
    "pipeline_stage": "stage_sort_key",
    "priority": "rating.priority",
    "short_term_value": "rating.short_term_value",
    "long_term_value": "rating.long_term_value",
}

# Contacted people and organizations with no live deal, or only deals at
# "not in pipeline", go below everyone in the pipeline, whatever the sort.
OUT_OF_PIPELINE_LAST = "cardinality(array_remove(deal_stages, 'not_in_pipeline')) = 0"

# Sorts that start high-to-low: newest contact first, highest value first.
# (Priority starts ascending: 1 is the best.)
DESCENDING_SORTS = ("last_contact", "newest", "short_term_value", "long_term_value")


def validate_feed_filters(kind: str, stage: str, sort: str) -> None:
    if kind not in KINDS:
        raise ValueError("Unknown contact type")
    if stage not in ("", "none", *PIPELINE_STAGES):
        raise ValueError("Unknown pipeline stage")
    if sort not in SORT_COLUMNS:
        raise ValueError("Unknown contact sort")


def feed_predicates(search: str, kind: str, stage: str, workspace_id: int | None) -> tuple[str, list]:
    """`stage` is one of the shown deals' stages ("none": no such deal). Contacts
    outside the pipeline stay listed; the feed sorts them last."""
    clauses, parameters = ["last_contact IS NOT NULL"], []
    if workspace_id is not None:
        clauses.append("workspace_id=%s")
        parameters.append(workspace_id)
    if kind:
        clauses.append("kind=%s")
        parameters.append(kind)
    if stage == "none":
        clauses.append("cardinality(deal_stages) = 0")
    elif stage:
        clauses.append("%s = ANY(deal_stages)")
        parameters.append(stage)
    for word in search.split()[:4]:
        pattern = "%" + word.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        clauses.append("(" + " OR ".join(
            f"{column} ILIKE %s ESCAPE '!'" for column in ("name", "description", "company", "city", "email", "phone", "searchable_people")
        ) + ")")
        parameters.extend([pattern] * 7)
    return " AND ".join(clauses) or "TRUE", parameters


def get_contact_feed(*, search: str = "", kind: str = "", stage: str = "", sort: str = "last_contact",
                     page: int = 1, workspace_id: int | None = None, extra_row: bool = False,
                     offer: str | None = CONSULTING,
                     dir: str | None = None, user_id: int | None = None) -> list[dict]:
    """One page of contacted people and organizations. `offer` picks whose stage
    each row shows (None: every offer's, in `deals`); those not in its pipeline
    come last. With `user_id`, each row carries that user's private ratings."""
    validate_feed_filters(kind, stage, sort)
    if page < 1:
        raise ValueError("Page must be positive")
    predicate, parameters = feed_predicates(search, kind, stage, workspace_id)
    default_direction = "desc" if sort in DESCENDING_SORTS else "asc"
    direction = "DESC" if (dir or default_direction) == "desc" else "ASC"
    tie_breaker = "kind, id DESC" if sort in ("last_contact", "newest") else "kind, id"
    order = f"{OUT_OF_PIPELINE_LAST}, {SORT_COLUMNS[sort]} {direction} NULLS LAST, {tie_breaker}"
    query = contact_feed_sql(offer) + f" WHERE {predicate} ORDER BY {order} LIMIT %s OFFSET %s"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(query, [user_id, user_id] + parameters + [PAGE_SIZE + int(extra_row), (page - 1) * PAGE_SIZE])
        return [serialize_row(dict(row)) for row in cursor.fetchall()]
