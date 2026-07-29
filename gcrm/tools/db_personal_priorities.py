"""Private per-user priority persistence for contacts."""

from gcrm.db.connection import db


def get_personal_priority(
    user_id: int,
    workspace_id: int,
    contact_id: int,
) -> int | None:
    """Return one user's priority when the contact is in the same workspace."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT priority
            FROM contact_user_priorities
            WHERE user_id = %s
              AND workspace_id = %s
              AND contact_id = %s
            """,
            (user_id, workspace_id, contact_id),
        )
        row = cursor.fetchone()
        return row["priority"] if row else None


def set_personal_priority(
    user_id: int,
    workspace_id: int,
    contact_id: int,
    priority: int | None,
) -> tuple[bool, int | None]:
    """Set or clear a priority, returning (contact_found, stored_priority)."""
    if priority is not None and priority not in range(1, 6):
        raise ValueError("Personal priority must be between 1 and 5")

    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM contacts c
            JOIN users u
              ON u.id = %s
             AND u.workspace_id = %s
             AND u.is_active = TRUE
            WHERE c.id = %s
              AND c.workspace_id = u.workspace_id
              AND c.deleted_at IS NULL
            """,
            (user_id, workspace_id, contact_id),
        )
        if cursor.fetchone() is None:
            return False, None

        if priority is None:
            cursor.execute(
                """
                DELETE FROM contact_user_priorities
                WHERE user_id = %s
                  AND workspace_id = %s
                  AND contact_id = %s
                """,
                (user_id, workspace_id, contact_id),
            )
            return True, None

        cursor.execute(
            """
            INSERT INTO contact_user_priorities (
                workspace_id, user_id, contact_id, priority
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, contact_id)
            DO UPDATE SET
                priority = EXCLUDED.priority,
                workspace_id = EXCLUDED.workspace_id,
                updated_at = NOW()
            RETURNING priority
            """,
            (workspace_id, user_id, contact_id, priority),
        )
        return True, cursor.fetchone()["priority"]
