import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

router = APIRouter(prefix="/drafts", tags=["drafts"], dependencies=[Depends(require_login)])
logger = logging.getLogger(__name__)


def _list_or_redirect(request: Request, drafts: list[dict]):
    """The list page's Drop button posts via htmx (expects the refreshed
    fragment back); the full-page draft view posts a plain form (expects a
    normal redirect back to the list)."""
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/drafts_list.html", {"request": request, "drafts": drafts})
    return local_redirect("/drafts/")

# Held drafts target either an organization (contact_id) or a person
# (person_id) — see gcrm/db/migrations/045_approval_queue_person_target.sql.
# Every query below resolves the recipient with a LEFT JOIN to both and
# COALESCE, since exactly one side is ever populated per row.
_RECIPIENT_JOIN = """
    FROM approval_queue aq
    LEFT JOIN contacts c ON c.id = aq.contact_id
    LEFT JOIN people p ON p.id = aq.person_id
"""


def _fetch_held_drafts(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            aq.id,
            aq.draft_subject,
            aq.created_at,
            aq.reviewer_note,
            aq.contact_id,
            aq.person_id,
            COALESCE(c.name, p.name)         AS recipient_name,
            COALESCE(c.city, p.city)         AS city,
            COALESCE(c.country, p.country)   AS country,
            c.type                            AS organization_type,
            COALESCE(c.email, p.email)       AS email,
            COALESCE(c.notes, p.notes)       AS recipient_notes
        {_RECIPIENT_JOIN}
        WHERE aq.status = 'on_hold'
        ORDER BY city, recipient_name
    """)
    return [dict(row) for row in cur.fetchall()]


def _fetch_draft(conn, item_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            aq.id, aq.draft_subject, aq.draft_body, aq.created_at, aq.reviewer_note,
            aq.contact_id, aq.person_id,
            COALESCE(c.name, p.name)   AS recipient_name,
            COALESCE(c.email, p.email) AS email,
            COALESCE(c.city, p.city)   AS city
        {_RECIPIENT_JOIN}
        WHERE aq.id = %s AND aq.status = 'on_hold'
    """, (item_id,))
    row = cur.fetchone()
    return dict(row) if row else None


@router.get("/", response_class=HTMLResponse)
def drafts_list(request: Request):
    with db() as conn:
        drafts = _fetch_held_drafts(conn)
    return templates.TemplateResponse("drafts.html", {"request": request, "drafts": drafts})


@router.get("/{item_id}", response_class=HTMLResponse)
def draft_detail(request: Request, item_id: int):
    with db() as conn:
        draft = _fetch_draft(conn, item_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found or not on hold")
    return templates.TemplateResponse("draft_detail.html", {"request": request, "draft": draft})


@router.post("/{item_id}/approve", response_class=HTMLResponse)
def approve(
    request: Request,
    item_id: int,
    final_subject: str = Form(default=""),
    final_body: str = Form(default=""),
    note: str = Form(default=""),
    _admin: str = Depends(require_admin),
):
    """Sends the draft — final_subject/final_body (from the full-page editor)
    override the stored draft when provided; the list page's quick actions
    omit them and the stored draft is sent as-is."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT aq.draft_subject, aq.draft_body, aq.contact_id, aq.person_id,
                   COALESCE(c.email, p.email) AS email
            {_RECIPIENT_JOIN}
            WHERE aq.id = %s AND aq.status = 'on_hold'
        """, (item_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found or not on hold")

    subject = final_subject.strip() or row["draft_subject"]
    body = final_body.strip() or row["draft_body"]

    try:
        from gcrm.tools.email import send_email
        success = send_email(to_email=row["email"] or "", subject=subject, body=body)
        if row["contact_id"]:
            from gcrm.tools.db import log_interaction
            log_interaction(
                contact_id=row["contact_id"],
                method="email",
                direction="outbound",
                summary=subject,
                outcome="no_reply",
            )
        else:
            from gcrm.tools.db_people_interactions import log_person_note
            log_person_note(row["person_id"], "email", f"Sent: {subject}")
    except Exception as error:
        logger.error("drafts approve send failed: item_id=%d error=%s", item_id, error)
        success = False

    final_status = "approved" if success else "approved_unsent"

    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE approval_queue
            SET status = %s, reviewed_at = NOW(), reviewer_note = %s,
                final_subject = %s, final_body = %s
            WHERE id = %s
        """, (final_status, note or None, subject, body, item_id))
        if row["contact_id"]:
            cur.execute("""
                UPDATE contacts SET status = 'contacted', updated_at = NOW()
                WHERE id = %s AND status NOT IN ('contacted', 'meeting', 'proposal')
            """, (row["contact_id"],))
        drafts = _fetch_held_drafts(conn)
    log_audit(None, None, "approval.approve", f"approval:{item_id}", final_status)

    return _list_or_redirect(request, drafts)


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

    return _list_or_redirect(request, drafts)
