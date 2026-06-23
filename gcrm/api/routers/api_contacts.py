"""Mobile contacts endpoints (JSON)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from gcrm.api.jwt_auth import require_jwt
from gcrm.db.connection import db

router = APIRouter(prefix="/api/contacts", tags=["mobile-contacts"])


def _serialize(row: dict) -> dict:
    r = dict(row)
    for key in ("created_at", "updated_at", "last_contact", "enriched_at"):
        if key in r and r[key] is not None:
            r[key] = r[key].isoformat()
    return r


@router.get("")
def list_contacts(
    search: str = Query(""),
    status: str = Query(""),
    page: int = Query(1, ge=1),
    _role: str = Depends(require_jwt),
) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        params: list = []
        where = ["c.deleted_at IS NULL"]
        if search:
            where.append("(c.name ILIKE %s OR c.city ILIKE %s OR c.type ILIKE %s)")
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if status:
            where.append("c.status = %s")
            params.append(status)
        where_clause = " AND ".join(where)
        offset = (page - 1) * 50
        cur.execute(
            f"""
            SELECT c.id, c.name, c.city, c.country, c.type, c.status,
                   c.email, c.website, c.fit_score, c.flagged, c.starred,
                   MAX(i.interaction_date) AS last_contact
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            WHERE {where_clause}
            GROUP BY c.id
            ORDER BY c.name ASC
            LIMIT 50 OFFSET %s
            """,
            params + [offset],
        )
        return [_serialize(dict(row)) for row in cur.fetchall()]


@router.get("/{contact_id}")
def get_contact(contact_id: int, _role: str = Depends(require_jwt)) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.*, MAX(i.interaction_date) AS last_contact
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            WHERE c.id = %s AND c.deleted_at IS NULL
            GROUP BY c.id
            """,
            [contact_id],
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
            {**dict(r), "interaction_date": r["interaction_date"].isoformat() if r["interaction_date"] else None}
            for r in cur.fetchall()
        ]
        return contact
