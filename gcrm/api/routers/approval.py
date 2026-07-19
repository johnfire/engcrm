import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.templates import templates
from gcrm.db.connection import db

router = APIRouter(prefix="/approvals", tags=["approvals"], dependencies=[Depends(require_login)])
logger = logging.getLogger(__name__)


def _fetch_pending(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            aq.id, aq.draft_subject, aq.draft_body, aq.created_at,
            c.id AS contact_id, c.name AS contact_name, c.city, c.email, c.website
        FROM approval_queue aq
        JOIN contacts c ON c.id = aq.contact_id
        WHERE aq.status = 'pending'
        ORDER BY aq.created_at ASC
    """)
    return [dict(row) for row in cur.fetchall()]


def _fetch_on_hold(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            aq.id, aq.draft_subject, aq.draft_body, aq.created_at,
            c.id AS contact_id, c.name AS contact_name, c.city, c.email, c.website
        FROM approval_queue aq
        JOIN contacts c ON c.id = aq.contact_id
        WHERE aq.status = 'on_hold'
        ORDER BY aq.created_at ASC
    """)
    return [dict(row) for row in cur.fetchall()]


def _fetch_rejected(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            aq.id, aq.draft_subject, aq.created_at, aq.reviewed_at, aq.reviewer_note,
            c.id AS contact_id, c.name AS contact_name, c.city, c.email
        FROM approval_queue aq
        JOIN contacts c ON c.id = aq.contact_id
        WHERE aq.status = 'rejected'
        ORDER BY aq.reviewed_at DESC
    """)
    return [dict(row) for row in cur.fetchall()]


def _send_and_log(item_id: int, contact_id: int, to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Attempt to send an approved email via SMTP. Returns (success, message)."""
    try:
        from gcrm.tools.db import log_interaction
        from gcrm.tools.email import send_email
        success = send_email(to_email=to_email, subject=subject, body=body)
        log_interaction(
            contact_id=contact_id,
            method="email",
            direction="outbound",
            summary=subject,
            outcome="no_reply",
        )
        # Mark as contacted on approval regardless of whether email sent
        with db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE contacts SET status = 'contacted', last_emailed_at = NOW(), updated_at = NOW() WHERE id = %s AND status IN ('cold', 'on_hold')",
                (contact_id,),
            )
        return success, "sent" if success else "approved_unsent"
    except Exception as error:
        logger.error("_send_and_log: item_id=%d error=%s", item_id, error)
        return False, str(error)


@router.get("/", response_class=HTMLResponse)
def approval_list(request: Request):
    with db() as conn:
        items = _fetch_pending(conn)
        on_hold = _fetch_on_hold(conn)
    return templates.TemplateResponse("approval.html", {"request": request, "items": items, "on_hold": on_hold})


@router.post("/{item_id}/approve", response_class=HTMLResponse)
def approve(request: Request, item_id: int, note: str = Form(default=""), _admin: str = Depends(require_admin)):
    # Atomically claim the item (pending/on_hold -> approved) so a concurrent or
    # double-clicked approve can't send the same draft twice — only the request
    # that wins the claim proceeds to send.
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue aq
            SET status = 'approved', reviewed_at = NOW(), reviewer_note = %s
            FROM contacts c
            WHERE aq.id = %s AND aq.status IN ('pending', 'on_hold') AND c.id = aq.contact_id
            RETURNING aq.draft_subject, aq.draft_body, aq.contact_id, c.email
        """, (note or None, item_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found or already reviewed")

    success, send_msg = _send_and_log(
        item_id=item_id,
        contact_id=row["contact_id"],
        to_email=row["email"] or "",
        subject=row["draft_subject"],
        body=row["draft_body"],
    )

    # Already claimed as 'approved'; downgrade only if the send failed.
    if not success:
        with db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE approval_queue SET status = 'approved_unsent', reviewer_note = %s WHERE id = %s",
                ((note or send_msg) or None, item_id),
            )
    from gcrm.tools.db_audit import log_audit
    log_audit(
        request.session.get("email") or "shared-admin", "user", "approval.approve",
        f"approval:{item_id}", send_msg, request.state.correlation_id,
    )

    with db() as conn:
        items = _fetch_pending(conn)
        on_hold = _fetch_on_hold(conn)

    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items, "on_hold": on_hold})


@router.post("/{item_id}/reject", response_class=HTMLResponse)
def reject(request: Request, item_id: int, note: str = Form(default=""), _admin: str = Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue
            SET status = 'rejected', reviewed_at = NOW(), reviewer_note = %s
            WHERE id = %s AND status IN ('pending', 'on_hold')
            RETURNING contact_id
        """, (note or None, item_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found or already reviewed")
        cur.execute(
            "UPDATE contacts SET status = 'dropped', updated_at = NOW() WHERE id = %s",
            (row["contact_id"],),
        )
        items = _fetch_pending(conn)
        on_hold = _fetch_on_hold(conn)
    from gcrm.tools.db_audit import log_audit
    log_audit(
        request.session.get("email") or "shared-admin", "user", "approval.reject",
        f"approval:{item_id}", "rejected", request.state.correlation_id,
    )
    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items, "on_hold": on_hold})


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def delete_draft(request: Request, item_id: int, _admin: str = Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM approval_queue WHERE id = %s", (item_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        items = _fetch_pending(conn)
        on_hold = _fetch_on_hold(conn)
    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items, "on_hold": on_hold})


@router.get("/dropped/", response_class=HTMLResponse)
def dropped_list(request: Request):
    with db() as conn:
        items = _fetch_rejected(conn)
    return templates.TemplateResponse("dropped.html", {"request": request, "items": items})


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def edit_and_approve(
    request: Request,
    item_id: int,
    final_subject: str = Form(...),
    final_body: str = Form(...),
    note: str = Form(default=""),
    _admin: str = Depends(require_admin),
):
    # Atomically claim (pending -> edited) so a concurrent edit/approve can't
    # re-send the same item; only the claim winner proceeds to send.
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue aq
            SET status = 'edited', reviewed_at = NOW(), reviewer_note = %s,
                final_subject = %s, final_body = %s
            FROM contacts c
            WHERE aq.id = %s AND aq.status = 'pending' AND c.id = aq.contact_id
            RETURNING aq.contact_id, c.email
        """, (note or None, final_subject, final_body, item_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found or already reviewed")

    success, send_msg = _send_and_log(
        item_id=item_id,
        contact_id=row["contact_id"],
        to_email=row["email"] or "",
        subject=final_subject,
        body=final_body,
    )

    # Already claimed as 'edited'; downgrade only if the send failed.
    if not success:
        with db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE approval_queue SET status = 'edited_unsent', reviewer_note = %s WHERE id = %s",
                ((note or send_msg) or None, item_id),
            )

    with db() as conn:
        items = _fetch_pending(conn)

    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items})
