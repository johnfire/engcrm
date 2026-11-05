"""Serialize the final recipient check with opt-outs before approved mail leaves."""
from fastapi import HTTPException

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit


def _person_organization_ids(cursor, person_id: int) -> set[int]:
    cursor.execute("SELECT contact_id,linked_contact_id FROM people WHERE id=%s AND deleted_at IS NULL FOR UPDATE", (person_id,))
    person = cursor.fetchone()
    if not person:
        raise HTTPException(403, "Recipient no longer available")
    return {person[key] for key in ("contact_id", "linked_contact_id") if person[key]}


def require_recipient_permission(cursor, contact_id: int | None, person_id: int | None = None) -> None:
    organization_ids = {contact_id} if contact_id is not None else set()
    if person_id is not None:
        organization_ids.update(_person_organization_ids(cursor, person_id))
    for organization_id in sorted(organization_ids):
        cursor.execute("SELECT name,do_not_contact,deleted_at FROM contacts WHERE id=%s FOR UPDATE", (organization_id,))
        organization = cursor.fetchone()
        if not organization or organization["deleted_at"] or organization["name"] == "[removed]" or organization["do_not_contact"]:
            raise HTTPException(403, "Recipient is suppressed or no longer available")
        cursor.execute("SELECT 1 FROM consent_log WHERE contact_id=%s AND (opt_out OR erasure_requested) LIMIT 1", (organization_id,))
        if cursor.fetchone():
            raise HTTPException(403, "Recipient has opted out or requested erasure")


def require_draft_permission(draft_id: int) -> None:
    try:
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT contact_id,person_id FROM approval_queue WHERE id=%s", (draft_id,))
            draft = cursor.fetchone()
            if not draft:
                raise HTTPException(404, "Draft not found")
            require_recipient_permission(cursor, draft["contact_id"], draft["person_id"])
    except HTTPException:
        log_audit(None, None, "approval.send_refused", f"approval:{draft_id}", "recipient_unavailable_or_suppressed")
        raise


def send_reviewed_email(contact_id: int | None, person_id: int | None = None, *, draft_id: int, **message) -> bool:
    from gcrm.tools.email import send_email

    try:
        with db() as connection:
            require_recipient_permission(connection.cursor(), contact_id, person_id)
            return send_email(**message)
    except HTTPException:
        with db() as connection:
            connection.cursor().execute(
                "UPDATE approval_queue SET status='approved_unsent',reviewer_note='Blocked: recipient suppressed or unavailable' "
                "WHERE id=%s AND status IN ('approved','edited')", (draft_id,),
            )
        log_audit(None, None, "outreach.send_refused", f"approval:{draft_id}", "suppressed")
        raise
