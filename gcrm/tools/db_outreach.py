"""Outreach quality-loop database operations (warm-reply outcomes)."""
import logging

from gcrm.db.connection import db, serialize_row

logger = logging.getLogger(__name__)


def record_warm_outcome(contact_id: int) -> None:
    """
    Record that a contact sent a warm/interested reply.
    Looks up the most recent outbound and inbound interactions for the contact,
    and the most recently approved queue item for word count.
    Silently skips if no outbound interaction exists yet.
    """
    with db() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id FROM interactions
            WHERE contact_id = %s AND direction = 'outbound' AND method = 'email'
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact_id,),
        )
        sent_row = cur.fetchone()
        if not sent_row:
            logger.info("record_warm_outcome: no outbound interaction found for contact_id=%d — skipping", contact_id)
            return
        sent_interaction_id = sent_row["id"]

        cur.execute(
            """
            SELECT id FROM interactions
            WHERE contact_id = %s AND direction = 'inbound' AND method = 'email'
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact_id,),
        )
        reply_row = cur.fetchone()
        reply_interaction_id = reply_row["id"] if reply_row else None

        cur.execute(
            """
            SELECT draft_body FROM approval_queue
            WHERE contact_id = %s AND status IN ('approved', 'approved_unsent')
            ORDER BY COALESCE(reviewed_at, created_at) DESC LIMIT 1
            """,
            (contact_id,),
        )
        queue_row = cur.fetchone()
        word_count = len(queue_row["draft_body"].split()) if queue_row else None

        cur.execute(
            """
            INSERT INTO outreach_outcomes
                (contact_id, sent_interaction_id, reply_interaction_id, warm, word_count)
            VALUES (%s, %s, %s, true, %s)
            ON CONFLICT (sent_interaction_id) DO NOTHING
            """,
            (contact_id, sent_interaction_id, reply_interaction_id, word_count),
        )
        logger.info("record_warm_outcome: recorded for contact_id=%d word_count=%s", contact_id, word_count)


def get_outreach_outcomes(days: int = 90) -> list[dict]:
    """Return outreach_outcomes with sent email bodies for the last N days."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                oo.id, oo.contact_id, oo.warm, oo.word_count, oo.created_at,
                aq.draft_subject, aq.draft_body,
                c.name AS contact_name, c.city, c.type AS organization_type
            FROM outreach_outcomes oo
            JOIN contacts c ON c.id = oo.contact_id
            LEFT JOIN LATERAL (
                SELECT draft_subject, draft_body
                FROM approval_queue
                WHERE contact_id = oo.contact_id
                  AND status IN ('approved', 'approved_unsent')
                ORDER BY COALESCE(reviewed_at, created_at) DESC
                LIMIT 1
            ) aq ON true
            WHERE oo.created_at >= NOW() - %s * INTERVAL '1 day'
            ORDER BY oo.created_at DESC
            """,
            (days,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]
