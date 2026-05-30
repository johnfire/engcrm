import logging
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from gcrm.db.connection import db
from gcrm.api.auth import require_login

router = APIRouter(prefix="/approvals", tags=["approvals"], dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))
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
        from gcrm.tools.email import send_email
        from gcrm.tools.db import log_interaction
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
    except Exception as e:
        logger.error("_send_and_log: item_id=%d error=%s", item_id, e)
        return False, str(e)


@router.get("/", response_class=HTMLResponse)
def approval_list(request: Request):
    with db() as conn:
        items = _fetch_pending(conn)
        on_hold = _fetch_on_hold(conn)
    return templates.TemplateResponse("approval.html", {"request": request, "items": items, "on_hold": on_hold})


@router.post("/{item_id}/approve", response_class=HTMLResponse)
def approve(request: Request, item_id: int, note: str = Form(default="")):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT aq.draft_subject, aq.draft_body, aq.contact_id, c.email
            FROM approval_queue aq JOIN contacts c ON c.id = aq.contact_id
            WHERE aq.id = %s AND aq.status IN ('pending', 'on_hold')
        """, (item_id,))
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
    final_status = "approved" if success else "approved_unsent"

    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue
            SET status = %s, reviewed_at = NOW(), reviewer_note = %s
            WHERE id = %s
        """, (final_status, (note or send_msg) or None, item_id))
        items = _fetch_pending(conn)
        on_hold = _fetch_on_hold(conn)

    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items, "on_hold": on_hold})


@router.post("/{item_id}/reject", response_class=HTMLResponse)
def reject(request: Request, item_id: int, note: str = Form(default="")):
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
    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items, "on_hold": on_hold})


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def delete_draft(request: Request, item_id: int):
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
):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT aq.contact_id, c.email
            FROM approval_queue aq JOIN contacts c ON c.id = aq.contact_id
            WHERE aq.id = %s AND aq.status = 'pending'
        """, (item_id,))
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
    final_status = "edited" if success else "edited_unsent"

    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue
            SET status = %s, reviewed_at = NOW(), reviewer_note = %s,
                final_subject = %s, final_body = %s
            WHERE id = %s
        """, (final_status, (note or send_msg) or None, final_subject, final_body, item_id))
        items = _fetch_pending(conn)

    return templates.TemplateResponse("partials/approval_list.html", {"request": request, "items": items})
