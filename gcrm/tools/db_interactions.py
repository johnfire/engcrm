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


def get_organization_interactions(contact_id: int) -> list[dict]:
    """Return interactions newest first."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT interaction_date, method, direction, summary, outcome FROM interactions WHERE contact_id = %s ORDER BY interaction_date DESC",
            (contact_id,),
        )
        return [serialize_row(dict(row)) for row in cursor.fetchall()]
