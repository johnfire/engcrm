"""User-account database operations (web-UI authentication)."""
from gcrm.db.connection import db, serialize_row


def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email (case-insensitive). Returns None if absent."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, password_hash, role, is_active, token_version "
            "FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        return cur.fetchone()


def get_user_token_version(user_id: int) -> int | None:
    """Current token version for an ACTIVE user, or None if the user is missing
    or disabled. A None or mismatch revokes the caller's bearer token."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT token_version FROM users WHERE id = %s AND is_active = TRUE",
            (user_id,),
        )
        row = cur.fetchone()
        return row["token_version"] if row else None


def create_user(email: str, password_hash: str, role: str = "admin", name: str = "") -> int:
    """Insert a new user and return its id. Raises on duplicate email."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, name, password_hash, role) "
            "VALUES (LOWER(%s), %s, %s, %s) RETURNING id",
            (email, name, password_hash, role),
        )
        return cur.fetchone()["id"]


def set_user_password(email: str, password_hash: str) -> bool:
    """Update a user's password hash. Returns False if no such user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s, token_version = token_version + 1 "
            "WHERE LOWER(email) = LOWER(%s)",
            (password_hash, email),
        )
        return cur.rowcount > 0


def set_user_active(email: str, is_active: bool) -> bool:
    """Enable or disable a user. Returns False if no such user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_active = %s, token_version = token_version + 1 "
            "WHERE LOWER(email) = LOWER(%s)",
            (is_active, email),
        )
        return cur.rowcount > 0


def list_users() -> list[dict]:
    """All users, newest first, without password hashes."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, role, is_active, created_at, last_login_at "
            "FROM users ORDER BY created_at DESC"
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def touch_user_login(user_id: int) -> None:
    """Record a successful login timestamp for a user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
