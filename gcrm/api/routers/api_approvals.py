"""Mobile approval-queue endpoints (JSON)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt, require_jwt_payload
from gcrm.db.connection import db
from gcrm.tools.db import serialize_row

router = APIRouter(prefix="/api/approvals", tags=["mobile-approvals"])


def _fetch_pending(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT aq.id, aq.draft_subject, aq.draft_body, aq.created_at,
               c.id AS contact_id, c.name, c.city, c.email, c.website
        FROM approval_queue aq
        JOIN contacts c ON c.id = aq.contact_id
        WHERE aq.status = 'pending'
        ORDER BY aq.created_at ASC
        """
    )
    return [serialize_row(dict(row)) for row in cur.fetchall()]


@router.get("")
def list_approvals(_role: str = Depends(require_jwt)) -> list[dict]:
    with db() as conn:
        return _fetch_pending(conn)


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/{approval_id}/approve", status_code=204)
def approve(approval_id: int, payload: dict = Depends(require_jwt_payload)) -> None:
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE approval_queue SET status='approved', reviewed_at=NOW() WHERE id=%s AND status='pending'",
            [approval_id],
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Approval not found or already reviewed")
    from gcrm.tools.db_audit import log_audit
    log_audit(str(payload.get("uid", "shared-admin")), "user", "approval.approve", f"approval:{approval_id}", "approved")


@router.post("/{approval_id}/reject", status_code=204)
def reject(approval_id: int, body: RejectBody, payload: dict = Depends(require_jwt_payload)) -> None:
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE approval_queue
            SET status='rejected', reviewed_at=NOW(), reviewer_note=%s
            WHERE id=%s AND status='pending'
            """,
            [body.reason or None, approval_id],
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Approval not found or already reviewed")
    from gcrm.tools.db_audit import log_audit
    log_audit(
        str(payload.get("uid", "shared-admin")), "user", "approval.reject",
        f"approval:{approval_id}", "rejected",
    )
