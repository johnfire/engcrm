"""Private, verbatim message storage; all queries require account and workspace."""
from gcrm.db.connection import db, serialize_row

PUBLIC_COLUMNS = "id, title, body, version, created_at, updated_at"


def list_saved_messages(user_id: int, workspace_id: int) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT {PUBLIC_COLUMNS} FROM saved_linkedin_messages "
            "WHERE user_id=%s AND workspace_id=%s ORDER BY updated_at DESC, id DESC",
            (user_id, workspace_id),
        )
        return [serialize_row(dict(row)) for row in cursor.fetchall()]


def create_saved_message(user_id: int, workspace_id: int, title: str, body: str) -> dict:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO saved_linkedin_messages (user_id, workspace_id, title, body) "
            f"VALUES (%s, %s, %s, %s) RETURNING {PUBLIC_COLUMNS}",
            (user_id, workspace_id, title, body),
        )
        return serialize_row(dict(cursor.fetchone()))


def update_saved_message(
    user_id: int, workspace_id: int, message_id: int, title: str, body: str, version: int,
) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE saved_linkedin_messages SET title=%s, body=%s, version=version+1, updated_at=NOW() "
            f"WHERE id=%s AND user_id=%s AND workspace_id=%s AND version=%s RETURNING {PUBLIC_COLUMNS}",
            (title, body, message_id, user_id, workspace_id, version),
        )
        stored = cursor.fetchone()
        return serialize_row(dict(stored)) if stored else None


def owns_saved_message(user_id: int, workspace_id: int, message_id: int) -> bool:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM saved_linkedin_messages WHERE id=%s AND user_id=%s AND workspace_id=%s",
                       (message_id, user_id, workspace_id))
        return cursor.fetchone() is not None
