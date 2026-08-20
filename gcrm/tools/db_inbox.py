"""Inbox-message caching, classification, and bounce / visit flagging."""
import logging
from datetime import datetime

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

logger = logging.getLogger(__name__)


def save_inbox_message(
    message_id: str,
    from_email: str,
    subject: str,
    body: str,
    received_at: datetime,
) -> int:
    """Cache an inbox message from IMAP. Returns id, or 0 if duplicate."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM inbox_messages WHERE message_id = %s",
            (message_id,),
        )
        if cur.fetchone():
            return 0
        cur.execute(
            """
            INSERT INTO inbox_messages (message_id, from_email, subject, body, received_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (message_id, from_email, subject, body, received_at),
        )
        return cur.fetchone()["id"]


def get_unprocessed_inbox() -> list[dict]:
    """Return inbox messages not yet processed by the follow-up agent."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM inbox_messages WHERE processed = FALSE ORDER BY received_at ASC"
        )
        return [dict(row) for row in cur.fetchall()]


def mark_message_processed(inbox_message_id: int, contact_id: int | None) -> None:
    """Mark an inbox message as processed, linking it to a contact if matched."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE inbox_messages
            SET processed = TRUE, matched_contact_id = %s
            WHERE id = %s
            """,
            (contact_id, inbox_message_id),
        )


def save_inbox_classification(
    inbox_message_id: int,
    contact_id: int | None,
    classification: str,
    reasoning: str,
) -> None:
    """Persist the LLM classification + reasoning and mark the message processed."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE inbox_messages
            SET processed = TRUE,
                matched_contact_id = %s,
                classification = %s,
                classification_reasoning = %s
            WHERE id = %s
            """,
            (contact_id, classification, reasoning, inbox_message_id),
        )


def mark_bad_email(contact_id: int) -> None:
    """Mark a contact's email undeliverable and log a bounce interaction.

    A bounce says nothing about where the relationship stands, so it raises the
    email_bounced flag and leaves stage and status alone — a contact with a
    meeting booked keeps the meeting.
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET email_bounced = TRUE, updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )
        cur.execute(
            """
            INSERT INTO interactions
                (contact_id, interaction_date, method, direction, summary, outcome)
            VALUES (%s, NOW(), 'email', 'inbound', 'Delivery failure — email bounced', 'bounce')
            """,
            (contact_id,),
        )
        logger.info("mark_bad_email: contact_id=%d email_bounced", contact_id)
    log_audit(None, None, "contact.email_bounced", f"contact:{contact_id}", "true")


def set_visit_when_nearby(contact_id: int) -> None:
    """Flag a contact for a personal visit next time you're in the area."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET visit_when_nearby = TRUE, updated_at = NOW() WHERE id = %s",
            (contact_id,),
        )
        logger.info("set_visit_when_nearby: contact_id=%d flagged", contact_id)
    log_audit(None, None, "contact.visit_flagged", f"contact:{contact_id}", "flagged")
