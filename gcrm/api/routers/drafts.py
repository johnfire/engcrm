import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

router = APIRouter(prefix="/drafts", tags=["drafts"], dependencies=[Depends(require_login)])
logger = logging.getLogger(__name__)


def _fetch_held_drafts(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            aq.id,
            aq.draft_subject,
            aq.draft_body,
            aq.created_at,
            aq.reviewer_note,
            c.id          AS contact_id,
            c.name        AS contact_name,
            c.city,
            c.country,
            c.type        AS organization_type,
            c.email,
            c.website,
            c.notes       AS contact_notes
        FROM approval_queue aq
        JOIN contacts c ON c.id = aq.contact_id
        WHERE aq.status = 'on_hold'
        ORDER BY c.city, c.name
    """)
    return [dict(row) for row in cur.fetchall()]


@router.get("/", response_class=HTMLResponse)
def drafts_list(request: Request):
    with db() as conn:
        drafts = _fetch_held_drafts(conn)
    return templates.TemplateResponse("drafts.html", {"request": request, "drafts": drafts})


@router.post("/{item_id}/approve", response_class=HTMLResponse)
def approve(request: Request, item_id: int, note: str = Form(default=""), _admin: str = Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT aq.draft_subject, aq.draft_body, aq.contact_id, c.email
            FROM approval_queue aq JOIN contacts c ON c.id = aq.contact_id
            WHERE aq.id = %s AND aq.status = 'on_hold'
        """, (item_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found or not on hold")

    try:
        from gcrm.tools.db import log_interaction
        from gcrm.tools.email import send_email
        success = send_email(to_email=row["email"] or "", subject=row["draft_subject"], body=row["draft_body"])
        log_interaction(
            contact_id=row["contact_id"],
            method="email",
            direction="outbound",
            summary=row["draft_subject"],
            outcome="no_reply",
        )
    except Exception as error:
        logger.error("drafts approve send failed: item_id=%d error=%s", item_id, error)
        success = False

    final_status = "approved" if success else "approved_unsent"

    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue
            SET status = %s, reviewed_at = NOW(), reviewer_note = %s
            WHERE id = %s
        """, (final_status, note or None, item_id))
        cur.execute("""
            UPDATE contacts SET status = 'contacted', updated_at = NOW()
            WHERE id = %s AND status NOT IN ('contacted', 'meeting', 'proposal')
        """, (row["contact_id"],))
        drafts = _fetch_held_drafts(conn)
    log_audit(None, None, "approval.approve", f"approval:{item_id}", final_status)

    return templates.TemplateResponse("partials/drafts_list.html", {"request": request, "drafts": drafts})


@router.post("/{item_id}/reject", response_class=HTMLResponse)
def reject(request: Request, item_id: int, note: str = Form(default=""), _admin: str = Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue
            SET status = 'rejected', reviewed_at = NOW(), reviewer_note = %s
            WHERE id = %s AND status = 'on_hold'
        """, (note or None, item_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Draft not found or not on hold")
        drafts = _fetch_held_drafts(conn)
    log_audit(None, None, "approval.reject", f"approval:{item_id}", "rejected")

    return templates.TemplateResponse("partials/drafts_list.html", {"request": request, "drafts": drafts})
