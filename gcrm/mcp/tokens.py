"""Secret tokens for the remote MCP connector.

A connector (Claude, set up once on claude.ai) sends `Authorization: Bearer <token>` on
every request. Only a SHA-256 of the token is stored, so a database dump cannot be used
to connect; the token itself is shown once, when it is made (scripts/mcp_token.py), and
pasted into the connector's request header. A token acts as one user, in that user's
workspace, and stops working when revoked or when the user is deactivated.
"""
import hashlib
import secrets

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(user_id: int, label: str = "") -> str:
    """A new token for this user. Returns it once; it cannot be read back later."""
    token = "engcrm_" + secrets.token_urlsafe(32)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO mcp_tokens (user_id, token_sha256, label) VALUES (%s, %s, %s) RETURNING id",
                    (user_id, _sha256(token), label.strip()))
        token_id = cur.fetchone()["id"]
    log_audit(None, None, "mcp_token.created", f"user:{user_id}", f"token:{token_id}")
    return token


def verify_token(token: str) -> dict | None:
    """The account behind a live token, {token_id, user_id, workspace_id}, or None.
    Marks the token as used."""
    if not token or not token.startswith("engcrm_"):
        return None
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE mcp_tokens t SET last_used_at = NOW() FROM users u "
            "WHERE t.token_sha256 = %s AND t.revoked_at IS NULL AND u.id = t.user_id AND u.is_active "
            "RETURNING t.id AS token_id, u.id AS user_id, u.workspace_id",
            (_sha256(token),),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_tokens() -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT t.id, u.email, t.label, t.created_at, t.last_used_at, t.revoked_at "
                    "FROM mcp_tokens t JOIN users u ON u.id = t.user_id ORDER BY t.id")
        return [dict(row) for row in cur.fetchall()]


def revoke_token(token_id: int) -> bool:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE mcp_tokens SET revoked_at = NOW() WHERE id = %s AND revoked_at IS NULL", (token_id,))
        revoked = cur.rowcount > 0
    if revoked:
        log_audit(None, None, "mcp_token.revoked", f"token:{token_id}", "revoked")
    return revoked
