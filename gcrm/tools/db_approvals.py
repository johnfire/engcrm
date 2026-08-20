"""Consent and approval-queue persistence tools.

Kept separate from contact discovery so GDPR decisions and outbound drafts have a
small, auditable persistence boundary.
"""

import logging

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

logger = logging.getLogger(__name__)


def ensure_consent_log(contact_id: int, *, conn=None) -> None:
    """Create the legitimate-interest record if the contact has none yet."""

    def insert(connection) -> None:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM consent_log WHERE contact_id = %s LIMIT 1", (contact_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO consent_log (contact_id, legal_basis, first_contact_date) VALUES (%s, 'legitimate_interest', NOW())",
                (contact_id,),
            )

    if conn:
        insert(conn)
    else:
        with db() as connection:
            insert(connection)


def check_compliance(contact_id: int) -> bool:
    """Return whether the contact can lawfully receive outreach."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT opt_out, erasure_requested FROM consent_log WHERE contact_id = %s ORDER BY created_at DESC LIMIT 1",
            (contact_id,),
        )
        consent = cursor.fetchone()
        if consent and (consent["opt_out"] or consent["erasure_requested"]):
            return False
        cursor.execute("SELECT name, do_not_contact FROM contacts WHERE id = %s", (contact_id,))
        contact = cursor.fetchone()
        return bool(
            contact and contact["name"] != "[removed]" and not contact["do_not_contact"]
        )


def set_opt_out(contact_id: int) -> None:
    """Record an opt-out and immediately prevent further outreach.

    The flag rides alongside the pipeline position rather than replacing it, so
    an organization that opted out at proposal stage still reads as one that got
    that far — and no later status edit can quietly un-suppress it.
    """
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO consent_log (contact_id, legal_basis, opt_out, opt_out_date) VALUES (%s, 'legitimate_interest', TRUE, NOW())",
            (contact_id,),
        )
        cursor.execute(
            "UPDATE contacts SET do_not_contact = TRUE, updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )
    log_audit(None, None, "contact.opted_out", f"contact:{contact_id}", "do_not_contact")


def queue_for_approval(contact_id: int, run_id: int, subject: str, body: str) -> int:
    """Persist a draft then best-effort notify registered mobile devices."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO approval_queue (contact_id, agent_run_id, draft_subject, draft_body) VALUES (%s, %s, %s, %s) RETURNING id",
            (contact_id, run_id or None, subject, body),
        )
        queue_id = cursor.fetchone()["id"]
        cursor.execute("SELECT name FROM contacts WHERE id = %s", (contact_id,))
        row = cursor.fetchone()
    try:
        from gcrm.api.push import send_push_to_all

        send_push_to_all(
            title="New approval waiting",
            body=f"{row['name'] if row else 'a contact'} — {subject}",
            data={"screen": "approvals"},
        )
    except Exception as error:
        logger.debug("approval push notification failed (non-blocking): %s", error)
    log_audit(None, None, "approval.queued", f"approval:{queue_id}", "pending")
    return queue_id
