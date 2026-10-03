"""Contact interaction persistence tools."""

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit


def log_interaction(
    contact_id: int, method: str, direction: str, summary: str, outcome: str
) -> None:
    """Log an interaction and touch its contact."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, direction, summary, outcome) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)",
            (contact_id, method, direction, summary, outcome),
        )
        cursor.execute("UPDATE contacts SET updated_at = NOW() WHERE id = %s", (contact_id,))
    log_audit(None, None, "interaction.logged", f"contact:{contact_id}", outcome)


def log_meeting_note(
    contact_id: int,
    method: str | None,
    note: str,
    follow_up_date=None,
    follow_up_text: str | None = None,
) -> int:
    """Record a note about a meeting, call or visit on an organization, with an
    optional follow-up date. Direction is left empty (it is neither an outbound nor
    an inbound message) and no status changes: only an explicit stage change does that.
    The organization is touched so it sorts as recently active. Returns the row id."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO interactions "
            "(contact_id, interaction_date, method, summary, outcome, next_action, next_action_date) "
            "VALUES (%s, CURRENT_DATE, %s, %s, 'note', %s, %s) RETURNING id",
            (contact_id, method, note, follow_up_text or None, follow_up_date),
        )
        note_id = cursor.fetchone()["id"]
        cursor.execute("UPDATE contacts SET updated_at = NOW() WHERE id = %s", (contact_id,))
    log_audit(None, None, "interaction.note_added", f"contact:{contact_id}", method or "note")
    return note_id


def delete_meeting_note(contact_id: int, note_id: int) -> bool:
    """Soft-delete one note (a mistyped note on the road). False if it is not this
    organization's or is already gone."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE interactions SET deleted_at = NOW() "
            "WHERE id = %s AND contact_id = %s AND deleted_at IS NULL",
            (note_id, contact_id),
        )
        deleted = cursor.rowcount > 0
    if deleted:
        log_audit(None, None, "interaction.note_deleted", f"contact:{contact_id}", str(note_id))
    return deleted


def get_organization_interactions(contact_id: int) -> list[dict]:
    """Return interactions newest first."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT interaction_date, method, direction, summary, outcome FROM interactions "
            "WHERE contact_id = %s AND deleted_at IS NULL ORDER BY interaction_date DESC",
            (contact_id,),
        )
        return [serialize_row(dict(row)) for row in cursor.fetchall()]
