"""Mobile search: one box over organizations and people, for "who is this / do I
know someone there?" on the road. Read-only; any signed-in role."""
from fastapi import APIRouter, Depends, Query

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.db.connection import db

router = APIRouter(prefix="/api/search", tags=["mobile-search"])

MIN_QUERY = 2
MAX_TOKENS = 4
LIMIT = 15


def _like(token: str) -> str:
    """A substring pattern for ILIKE ... ESCAPE '!', with the user's ! % _ taken literally."""
    escaped = token.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


def _prefix(token: str) -> str:
    return _like(token)[1:]  # same escaping, anchored at the start


def _token_conditions(tokens: list[str], columns: list[str]) -> tuple[str, list[str]]:
    """Every word must match somewhere, so "anna roth" finds Anna Roth and
    "roth acme" finds Roth at Acme."""
    clauses, params = [], []
    for token in tokens:
        clauses.append("(" + " OR ".join(f"{col} ILIKE %s ESCAPE '!'" for col in columns) + ")")
        params += [_like(token)] * len(columns)
    return " AND ".join(clauses), params


@router.get("")
def search(
    q: str = Query("", max_length=100),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    """Organizations (by name or city) and people (by name, email, city or company),
    best matches first: a name that starts with the first word leads. Fewer than
    two characters returns nothing rather than the whole database."""
    tokens = q.split()[:MAX_TOKENS]
    if not tokens or len(q.strip()) < MIN_QUERY:
        return {"query": q, "organizations": [], "people": []}
    _, workspace_id = _personal_identity(payload)
    first_prefix = _prefix(tokens[0])

    org_where, org_params = _token_conditions(tokens, ["c.name", "c.city"])
    people_where, people_params = _token_conditions(
        tokens, ["p.name", "p.email", "p.city", "p.company_raw", "c.name"]
    )
    org_scope = " AND c.workspace_id = %s" if workspace_id is not None else ""
    people_scope = " AND p.workspace_id = %s" if workspace_id is not None else ""

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT c.id, c.name, c.city, c.country, c.type, c.pipeline_stage, c.status,
                   (SELECT COUNT(*) FROM people lp
                     WHERE lp.contact_id = c.id AND lp.is_linkedin_contact AND lp.deleted_at IS NULL
                   ) AS linkedin_connection_count
            FROM contacts c
            WHERE c.deleted_at IS NULL AND {org_where}{org_scope}
            ORDER BY (c.name ILIKE %s ESCAPE '!') DESC, lower(c.name), c.id
            LIMIT {LIMIT}
            """,
            org_params + ([workspace_id] if workspace_id is not None else []) + [first_prefix],
        )
        organizations = [dict(r) for r in cur.fetchall()]
        cur.execute(
            f"""
            SELECT p.id, p.name, p.title, p.city, p.pipeline_stage, p.is_linkedin_contact,
                   p.contact_id, COALESCE(c.name, p.company_raw) AS company,
                   c.pipeline_stage AS company_pipeline_stage
            FROM people p LEFT JOIN contacts c ON c.id = p.contact_id AND c.deleted_at IS NULL
            WHERE p.deleted_at IS NULL AND {people_where}{people_scope}
            ORDER BY (p.name ILIKE %s ESCAPE '!') DESC, lower(p.name), p.id
            LIMIT {LIMIT}
            """,
            people_params + ([workspace_id] if workspace_id is not None else []) + [first_prefix],
        )
        people = [dict(r) for r in cur.fetchall()]
    return {"query": q, "organizations": organizations, "people": people}
