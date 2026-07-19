"""Database operations for invitations and self-service account security."""
import hashlib
from datetime import datetime, timedelta, timezone

from gcrm.db.connection import db


def hash_one_time_token(token: str) -> str:
    """Return a non-reversible hash for a browser-delivered one-time token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_default_workspace_id() -> int:
    """Return the pre-existing CRM's workspace identifier."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def create_invitation(email: str, role: str, creator_id: int | None, token: str) -> None:
    """Store a 7-day invitation for the default workspace."""
    expiration = datetime.now(timezone.utc) + timedelta(days=7)
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO account_invitations
            (workspace_id, email, role, token_hash, expires_at, created_by_user_id)
            VALUES (%s, LOWER(%s), %s, %s, %s, %s)""",
            (get_default_workspace_id(), email, role, hash_one_time_token(token), expiration, creator_id),
        )


def accept_invitation(email: str, password_hash: str, token: str, name: str) -> int | None:
    """Atomically consume a valid invitation and create its user account."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE account_invitations SET accepted_at = NOW()
            WHERE token_hash = %s AND LOWER(email) = LOWER(%s)
              AND accepted_at IS NULL AND expires_at > NOW()
            RETURNING workspace_id, role""",
            (hash_one_time_token(token), email),
        )
        invitation = cursor.fetchone()
        if not invitation:
            return None
        cursor.execute(
            """INSERT INTO users (email, name, password_hash, role, workspace_id)
            VALUES (LOWER(%s), %s, %s, %s, %s) RETURNING id""",
            (email, name, password_hash, invitation["role"], invitation["workspace_id"]),
        )
        return cursor.fetchone()["id"]


def set_user_totp(user_id: int, encrypted_secret: str) -> None:
    """Enable TOTP after its setup code was verified."""
    with db() as conn:
        conn.cursor().execute(
            "UPDATE users SET mfa_secret_encrypted = %s, mfa_enabled = TRUE WHERE id = %s",
            (encrypted_secret, user_id),
        )


def get_user_totp(user_id: int) -> str | None:
    """Return the encrypted TOTP seed for an enabled user."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mfa_secret_encrypted FROM users WHERE id = %s AND mfa_enabled = TRUE", (user_id,))
        row = cursor.fetchone()
        return row["mfa_secret_encrypted"] if row else None
