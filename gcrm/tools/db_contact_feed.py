"""Workspace-scoped businesses with contacted people grouped underneath."""
from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.pipeline_days import MEASURED_STAGES, days_to_customer
from gcrm.tools.db_contact_feed_query import contact_feed_sql
from gcrm.tools.db_deals import CONSULTING

PAGE_SIZE = 50
KINDS = ("", "person", "organization")

# The Days column in SQL, for sorting and averaging (the same rule as pipeline_days.days_to_customer, which
# fills the column on screen; an integration test holds the two together): days from the first contact to
# the day they became a customer, or to today while they are not one yet; NULL for a stage that is not
# measured, no contact yet, or a customer whose date was never recorded.
_MEASURED_LIST = ", ".join(f"'{stage}'" for stage in MEASURED_STAGES)
DAYS_SQL = (f"(CASE WHEN first_contact IS NULL OR NOT deal_stages && ARRAY[{_MEASURED_LIST}]::text[] THEN NULL "
            "WHEN 'customer' = ANY(deal_stages) THEN CASE WHEN customer_since IS NULL THEN NULL "
            "ELSE GREATEST(customer_since::date - first_contact::date, 0) END "
            "ELSE GREATEST(CURRENT_DATE - first_contact::date, 0) END)")
# The one measured stage a row counts under: its strongest (a customer in any offer is a customer).
STAGE_SQL = ("CASE " + " ".join(f"WHEN '{stage}' = ANY(deal_stages) THEN '{stage}'" for stage in reversed(MEASURED_STAGES))
             + " END")

SORT_COLUMNS = {
    "last_contact": "last_contact",
    "first_contact": "first_contact",
    "days": DAYS_SQL,
    "newest": "last_contact",  # Older mobile clients use this sort key.
    "name": "lower(name)",
    "city": "lower(city)",
    "kind": "kind",
    "pipeline_stage": "stage_sort_key",
    "status": "status_sort_key",
    "next_contact": "next_contact",
    "total_value": "total_value",
    "priority": "rating.priority",
    "short_term_value": "rating.short_term_value",
    "long_term_value": "rating.long_term_value",
}

# Sorts that start high-to-low: newest contact first, highest value first.
# (Priority starts ascending: 1 is the best.)
DESCENDING_SORTS = ("last_contact", "newest", "first_contact", "days", "short_term_value", "long_term_value", "total_value")


def validate_feed_filters(kind: str, stage: str, sort: str, then: str = "") -> None:
    if kind not in KINDS:
        raise ValueError("Unknown contact type")
    if stage not in ("", "none", *PIPELINE_STAGES):
        raise ValueError("Unknown pipeline stage")
    if sort not in SORT_COLUMNS:
        raise ValueError("Unknown contact sort")
    if then and then not in SORT_COLUMNS:
        raise ValueError("Unknown second contact sort")


def feed_predicates(search: str, kind: str, stage: str, workspace_id: int | None) -> tuple[str, list]:
    """`stage` is one of the shown deals' stages ("none": no such deal). Everyone
    contacted is listed, whatever their stage: a dated activity, or a deal status
    that says they were reached (CONTACTED_STATUSES) even with no date yet."""
    clauses, parameters = ["(last_contact IS NOT NULL OR contacted)"], []
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


def _direction(sort: str, chosen: str | None) -> str:
    """SQL direction for a sort: the one asked for, else the natural one (newest and biggest first)."""
    return "DESC" if (chosen or ("desc" if sort in DESCENDING_SORTS else "asc")) == "desc" else "ASC"


def get_contact_feed(*, search: str = "", kind: str = "", stage: str = "", sort: str = "last_contact",
                     page: int = 1, workspace_id: int | None = None, extra_row: bool = False,
                     offer: str | None = CONSULTING,
                     dir: str | None = None, user_id: int | None = None,
                     then: str = "", then_dir: str | None = None) -> list[dict]:
    """One page of contacted people and organizations. `offer` picks whose stage
    each row shows (None: every offer's, in `deals`); the stage never moves a
    row, only the chosen sort does. Undated contacts sort after dated ones.
    With `user_id`, each row carries that user's private ratings. `then` is a second column that orders the
    rows within each value of the first (its own direction in `then_dir`)."""
    validate_feed_filters(kind, stage, sort, then)
    if page < 1:
        raise ValueError("Page must be positive")
    predicate, parameters = feed_predicates(search, kind, stage, workspace_id)
    tie_breaker = "kind, id DESC" if sort in ("last_contact", "newest") else "kind, id"
    order = f"{SORT_COLUMNS[sort]} {_direction(sort, dir)} NULLS LAST"
    if then and then != sort:
        order += f", {SORT_COLUMNS[then]} {_direction(then, then_dir)} NULLS LAST"
    order += f", {tie_breaker}"
    query = contact_feed_sql(offer) + f" WHERE {predicate} ORDER BY {order} LIMIT %s OFFSET %s"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(query, [user_id, user_id] + parameters + [PAGE_SIZE + int(extra_row), (page - 1) * PAGE_SIZE])
        rows = [serialize_row(dict(row)) for row in cursor.fetchall()]
    for row in rows:
        row["days_to_customer"] = days_to_customer(row["deals"], row["first_contact"], row["customer_since"])
    return rows


def get_stage_means(*, search: str = "", kind: str = "", workspace_id: int | None = None,
                    offer: str | None = CONSULTING) -> dict:
    """The mean of the Days column for each measured stage (nibble, prospect, opportunity, customer) and for
    all of them together, over the contacts the list shows for this search, kind and offer (the stage filter
    is left out, so every stage stays in view). A contact without a Days figure (a dash) is not counted in
    the mean. `contacts` is everyone at that stage, `counted` those with a figure, `mean` whole days or None.
    A contact counts under its strongest measured stage."""
    predicate, parameters = feed_predicates(search, kind, "", workspace_id)
    columns = f"{STAGE_SQL} AS stage, COUNT(*) AS contacts, COUNT({DAYS_SQL}) AS counted, COALESCE(SUM({DAYS_SQL}), 0) AS total_days"
    query = contact_feed_sql(offer, columns) + f" WHERE {predicate} GROUP BY 1"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(query, [None, None] + parameters)
        found = {row["stage"]: row for row in cursor.fetchall() if row["stage"]}

    def summary(contacts: int, counted: int, total: int) -> dict:
        return {"contacts": contacts, "counted": counted, "mean": round(total / counted) if counted else None}

    stages = []
    for stage in MEASURED_STAGES:
        row = found.get(stage)
        stages.append({"stage": stage, **summary(*((row["contacts"], row["counted"], int(row["total_days"])) if row else (0, 0, 0)))})
    everyone = summary(sum(s["contacts"] for s in stages), sum(s["counted"] for s in stages),
                       sum(int(r["total_days"]) for r in found.values()))
    return {"stages": stages, "all": everyone}
