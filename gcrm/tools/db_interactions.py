"""Contact interaction persistence tools."""

from gcrm.activity_types import VISIT_METHODS
from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit


def log_interaction(
    contact_id: int, method: str, direction: str, summary: str, outcome: str, offer_id: int | None = None,
) -> None:
    """Log an interaction and touch its contact. `offer_id` is the offer it was
    about (None: general)."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, direction, summary, outcome, offer_id) "
            "VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s)",
            (contact_id, method, direction, summary, outcome, offer_id),
        )
        cursor.execute("UPDATE contacts SET updated_at = NOW() WHERE id = %s", (contact_id,))
    log_audit(None, None, "interaction.logged", f"contact:{contact_id}", outcome)


def log_meeting_note(
    contact_id: int,
    method: str | None,
    note: str,
    follow_up_date=None,
    follow_up_text: str | None = None,
    duration_minutes: int | None = None,
    offer_id: int | None = None,
    occurred_on=None,
    impression: str | None = None,
    materials_left: str | None = None,
) -> int:
    """Record a note about a meeting, call or visit on an organization: when it
    happened (`occurred_on`, default today), how it felt, what was left behind,
    any follow-up promised (with an optional date) and the offer it was about
    (None: general). Direction is left empty (it is neither an outbound nor
    an inbound message) and no status changes: only an explicit stage change does that.
    The organization is touched so it sorts as recently active. Returns the row id."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO interactions "
            "(contact_id, interaction_date, method, summary, outcome, next_action, next_action_date, "
            "duration_minutes, offer_id, impression, materials_left) "
            "VALUES (%s, COALESCE(%s::date, CURRENT_DATE), %s, %s, 'note', %s, %s, %s, %s, %s, %s) RETURNING id",
            (contact_id, occurred_on, method, note, follow_up_text or None, follow_up_date, duration_minutes,
             offer_id, impression, materials_left or None),
        )
        note_id = cursor.fetchone()["id"]
        cursor.execute("UPDATE contacts SET updated_at = NOW() WHERE id = %s", (contact_id,))
    log_audit(None, None, "interaction.note_added", f"contact:{contact_id}", method or "note")
    return note_id


def get_visit_summary(contact_id: int) -> dict:
    """What the logged activities say about visiting this organization: the last
    in-person visit (date and minutes), the first and last impression, and the
    latest materials left and follow-up promised. Each is None until logged."""
    live = "contact_id = %(id)s AND deleted_at IS NULL"
    activities = f"{live} AND method IS DISTINCT FROM 'next_step' AND method IS DISTINCT FROM 'next_step_done'"
    visits = f"{live} AND method IN ({', '.join(repr(m) for m in VISIT_METHODS)})"
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
              (SELECT interaction_date FROM interactions WHERE {visits}
                ORDER BY interaction_date DESC, id DESC LIMIT 1) AS last_visited,
              (SELECT duration_minutes FROM interactions WHERE {visits}
                ORDER BY interaction_date DESC, id DESC LIMIT 1) AS last_visit_minutes,
              (SELECT impression FROM interactions WHERE {activities} AND impression IS NOT NULL
                ORDER BY interaction_date, id LIMIT 1) AS first_impression,
              (SELECT impression FROM interactions WHERE {activities} AND impression IS NOT NULL
                ORDER BY interaction_date DESC, id DESC LIMIT 1) AS last_impression,
              (SELECT materials_left FROM interactions WHERE {activities} AND materials_left IS NOT NULL
                ORDER BY interaction_date DESC, id DESC LIMIT 1) AS materials_left,
              (SELECT next_action FROM interactions WHERE {activities} AND next_action IS NOT NULL
                ORDER BY interaction_date DESC, id DESC LIMIT 1) AS followup_promised
            """,
            {"id": contact_id},
        )
        return dict(cursor.fetchone())


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
