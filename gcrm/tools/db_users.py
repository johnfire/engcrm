"""User-account database operations (web-UI authentication)."""
from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit


def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email (case-insensitive). Returns None if absent."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, password_hash, role, is_active, token_version, "
            "workspace_id, ui_language FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        return cur.fetchone()


def get_user_by_id(user_id: int) -> dict | None:
    """Look up a user by id. Returns None if absent. Used by the mobile
    /api/auth/me endpoint, which only has uid (not email) from the JWT."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, role, is_active, token_version, "
            "workspace_id, ui_language FROM users WHERE id = %s",
            (user_id,),
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
            "INSERT INTO users (email, name, password_hash, role, workspace_id) "
            "VALUES (LOWER(%s), %s, %s, %s, "
            "(SELECT id FROM workspaces WHERE slug = 'default')) RETURNING id",
            (email, name, password_hash, role),
        )
        user_id = cur.fetchone()["id"]
    log_audit(None, None, "user.created", f"user:{user_id}", "created")
    return user_id


def set_user_password(email: str, password_hash: str) -> bool:
    """Update a user's password hash. Returns False if no such user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s, token_version = token_version + 1 "
            "WHERE LOWER(email) = LOWER(%s)",
            (password_hash, email),
        )
        updated = cur.rowcount > 0
    if updated:
        log_audit(None, None, "user.password_reset", f"user:{email}", "success")
    return updated


def set_user_password_by_id(user_id: int, password_hash: str) -> bool:
    """Like set_user_password, but keyed by id — used by the token-based reset
    flow, which only has the user_id from the consumed reset token."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s, token_version = token_version + 1 WHERE id = %s",
            (password_hash, user_id),
        )
        updated = cur.rowcount > 0
    if updated:
        log_audit(None, None, "user.password_reset", f"user:{user_id}", "success")
    return updated


def set_user_ui_language(user_id: int, language: str) -> bool:
    """Update a user's interface-language preference. Returns False if no
    such user. Caller must validate `language` against the allowed set
    first — this issues a raw UPDATE and relies on the DB CHECK constraint
    as a backstop, not a friendly error path."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET ui_language = %s WHERE id = %s",
            (language, user_id),
        )
        updated = cur.rowcount > 0
    if updated:
        log_audit(None, None, "user.ui_language_changed", f"user:{user_id}", language)
    return updated


def set_user_active(email: str, is_active: bool) -> bool:
    """Enable or disable a user. Returns False if no such user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_active = %s, token_version = token_version + 1 "
            "WHERE LOWER(email) = LOWER(%s)",
            (is_active, email),
        )
        updated = cur.rowcount > 0
    if updated:
        outcome = "activated" if is_active else "deactivated"
        log_audit(None, None, "user.status_changed", f"user:{email}", outcome)
    return updated


def list_users() -> list[dict]:
    """All users, newest first, without password hashes."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, name, role, is_active, workspace_id, created_at, last_login_at "
            "FROM users ORDER BY created_at DESC"
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def touch_user_login(user_id: int) -> None:
    """Record a successful login timestamp for a user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
