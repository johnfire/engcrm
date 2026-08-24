"""Timestamped note log per person — dictated or typed. Mirrors
`db_interactions.py` (which is scoped to `contacts`/organizations)."""
import logging

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit

logger = logging.getLogger(__name__)


def log_person_note(person_id: int, method: str | None, note: str) -> int:
    """Insert a note and touch the person's updated_at. Returns the new row id."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO people_interactions (person_id, method, note) VALUES (%s, %s, %s) RETURNING id",
            (person_id, method or None, note),
        )
        note_id = cursor.fetchone()["id"]
        cursor.execute("UPDATE people SET updated_at = NOW() WHERE id = %s", (person_id,))
    log_audit(None, None, "person.note_added", f"person:{person_id}", method or "note")
    return note_id


def get_person_interactions(person_id: int) -> list[dict]:
    """Return this person's notes, newest first, excluding soft-deleted entries."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, occurred_at, method, note FROM people_interactions "
            "WHERE person_id = %s AND deleted_at IS NULL ORDER BY occurred_at DESC",
            (person_id,),
        )
        return [serialize_row(dict(row)) for row in cursor.fetchall()]


def delete_person_interaction(person_id: int, note_id: int) -> bool:
    """Soft delete one note. Returns False if it doesn't exist under this person."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE people_interactions SET deleted_at = NOW() "
            "WHERE id = %s AND person_id = %s AND deleted_at IS NULL",
            (note_id, person_id),
        )
        deleted = cursor.rowcount > 0
    if deleted:
        log_audit(None, None, "person.note_deleted", f"person:{person_id}", f"note:{note_id}")
    return deleted
