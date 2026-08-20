"""Mobile contacts endpoints (JSON)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.db.connection import db
from gcrm.supervisor.contact_opportunity_analysis import analyse_contact_opportunity
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_opportunities import get_latest_opportunity_analysis
from gcrm.tools.db_personal_priorities import set_personal_priority
from gcrm.tools.db_users import get_user_by_id

router = APIRouter(prefix="/api/contacts", tags=["mobile-contacts"])

# Whitelisted so `sort` can be trusted straight into an f-string ORDER BY below.
SORT_COLUMNS = {
    "created_at": "c.created_at",
    "name":       "lower(c.name)",
    "type":       "lower(c.type)",
    "personal_priority": "cup.priority",
}


class PersonalPriorityBody(BaseModel):
    priority: int | None = None


def _personal_identity(payload: dict) -> tuple[int | None, int | None]:
    """Resolve the real account behind a JWT; shared admin has no identity."""
    user_id = payload.get("uid")
    if user_id is None:
        return None, None
    user = get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Account not found")
    return user_id, user["workspace_id"]


def _priority_join(user_id: int | None) -> tuple[str, list]:
    if user_id is None:
        return "LEFT JOIN contact_user_priorities cup ON FALSE", []
    return (
        "LEFT JOIN contact_user_priorities cup "
        "ON cup.contact_id = c.id AND cup.user_id = %s",
        [user_id],
    )


def _serialize(row: dict) -> dict:
    r = dict(row)
    for key in ("created_at", "updated_at", "last_contact", "enriched_at"):
        if key in r and r[key] is not None:
            r[key] = r[key].isoformat()
    return r


def _opportunity_payload(row: dict | None) -> dict | None:
    """Shape a stored opportunity assessment for the mobile detail screen.

    Mirrors the fields the web contact_detail template renders. The JSONB list
    fields arrive already deserialized from db_opportunities; analysis_date is a
    date/datetime that we render as an ISO string like every other timestamp."""
    if not row:
        return None
    analysis_date = row.get("analysis_date")
    return {
        "opportunity_score": row.get("opportunity_score"),
        "confidence_score": row.get("confidence_score"),
        "priority_score": row.get("priority_score"),
        "fit_reasoning": row.get("fit_reasoning"),
        "suggested_approach": row.get("suggested_approach"),
        "evidence": row.get("evidence") or [],
        "recommended_services": row.get("recommended_services") or [],
        "discovery_questions": row.get("discovery_questions") or [],
        "analysis_date": analysis_date.isoformat() if analysis_date else None,
        "model_used": row.get("model_used"),
    }


@router.get("")
def list_contacts(
    search: str = Query(""),
    status: str = Query(""),
    stage: str = Query(""),
    page: int = Query(1, ge=1),
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    personal_priority: str = Query(""),
    payload: dict = Depends(require_jwt_payload),
) -> list[dict]:
    sort_col = SORT_COLUMNS.get(sort, SORT_COLUMNS["created_at"])
    sort_dir = "DESC" if dir == "desc" else "ASC"
    user_id, workspace_id = _personal_identity(payload)
    priority_join, priority_params = _priority_join(user_id)
    with db() as conn:
        cur = conn.cursor()
        filter_params: list = []
        where = ["c.deleted_at IS NULL"]
        if search:
            where.append("(c.name ILIKE %s OR c.city ILIKE %s OR c.type ILIKE %s)")
            filter_params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if status:
            where.append("c.status = %s")
            filter_params.append(status)
        if stage:
            where.append("c.pipeline_stage = %s")
            filter_params.append(stage)
        if personal_priority in {"1", "2", "3", "4", "5"}:
            where.append("cup.priority = %s")
            filter_params.append(int(personal_priority))
        elif personal_priority == "unrated":
            where.append("cup.priority IS NULL")
        if workspace_id is not None:
            where.append("c.workspace_id = %s")
            filter_params.append(workspace_id)
        where_clause = " AND ".join(where)
        offset = (page - 1) * 50
        cur.execute(
            f"""
            SELECT c.id, c.name, c.city, c.country, c.type,
                   c.pipeline_stage, c.status,
                   c.do_not_contact, c.email_bounced, c.research_exhausted,
                   c.email, c.website, c.fit_score, c.flagged, c.starred,
                   c.created_at, cup.priority AS personal_priority,
                   MAX(i.interaction_date) AS last_contact
            FROM contacts c
            {priority_join}
            LEFT JOIN interactions i ON i.contact_id = c.id
            WHERE {where_clause}
            GROUP BY c.id, cup.priority
            ORDER BY {sort_col} {sort_dir} NULLS LAST
            LIMIT 50 OFFSET %s
            """,
            priority_params + filter_params + [offset],
        )
        return [_serialize(dict(row)) for row in cur.fetchall()]


@router.get("/{contact_id}")
def get_contact(contact_id: int, payload: dict = Depends(require_jwt_payload)) -> dict:
    user_id, workspace_id = _personal_identity(payload)
    priority_join, priority_params = _priority_join(user_id)
    workspace_filter = "AND c.workspace_id = %s" if workspace_id is not None else ""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT c.*, cup.priority AS personal_priority,
                   MAX(i.interaction_date) AS last_contact
            FROM contacts c
            {priority_join}
            LEFT JOIN interactions i ON i.contact_id = c.id
            WHERE c.id = %s
              AND c.deleted_at IS NULL
              {workspace_filter}
            GROUP BY c.id, cup.priority
            """,
            priority_params
            + [contact_id]
            + ([workspace_id] if workspace_id is not None else []),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")
        contact = _serialize(dict(row))

        cur.execute(
            """
            SELECT interaction_date, method, direction, summary, outcome
            FROM interactions
            WHERE contact_id = %s
            ORDER BY interaction_date DESC
            LIMIT 20
            """,
            [contact_id],
        )
        contact["interactions"] = [
            {**dict(row), "interaction_date": row["interaction_date"].isoformat() if row["interaction_date"] else None}
            for row in cur.fetchall()
        ]

    contact["opportunity_analysis"] = _opportunity_payload(
        get_latest_opportunity_analysis(contact_id)
    )
    return contact


@router.put("/{contact_id}/personal-priority")
def update_personal_priority(
    contact_id: int,
    body: PersonalPriorityBody,
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    user_id, workspace_id = _personal_identity(payload)
    if user_id is None or workspace_id is None:
        raise HTTPException(status_code=403, detail="Personal account required")
    if body.priority is not None and body.priority not in range(1, 6):
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5")

    contact_found, stored_priority = set_personal_priority(
        user_id,
        workspace_id,
        contact_id,
        body.priority,
    )
    if not contact_found:
        raise HTTPException(status_code=404, detail="Contact not found")
    outcome = "cleared" if stored_priority is None else f"set:{stored_priority}"
    log_audit(
        None,
        None,
        "contact.personal_priority_changed",
        f"contact:{contact_id}",
        outcome,
    )
    return {"personal_priority": stored_priority}


@router.post("/{contact_id}/opportunity-analysis")
def run_opportunity_analysis(
    contact_id: int,
    _role: str = Depends(require_jwt_admin),
) -> dict:
    """Run a fresh opportunity assessment for one contact and return the result.

    Admin-only, matching the web contact-detail action. Synchronous: it fetches
    the company website, runs the LLM, and persists — so the caller should use a
    generous client timeout. It never sends outreach."""
    log_audit(None, None, "contact.opportunity_analysis_requested", f"contact:{contact_id}", "started")
    try:
        analyse_contact_opportunity(contact_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Contact not found")
    except Exception as error:
        log_audit(None, None, "contact.opportunity_analysis_requested", f"contact:{contact_id}", "failed")
        raise HTTPException(status_code=502, detail=f"Analysis failed: {error}")
    log_audit(None, None, "contact.opportunity_analysis_requested", f"contact:{contact_id}", "completed")
    return {
        "opportunity_analysis": _opportunity_payload(
            get_latest_opportunity_analysis(contact_id)
        )
    }
