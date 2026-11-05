"""Revocable, fixed-lifetime browser sessions; only token hashes are stored."""
import hashlib
import hmac
import secrets

from gcrm.config import SESSION_SECRET
from gcrm.db.connection import db


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _admin_fingerprint(password: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), password.encode(), hashlib.sha256).hexdigest()


def create_web_session(identity: dict, admin_password: str) -> str:
    token = secrets.token_urlsafe(32)
    emergency_hash = _admin_fingerprint(admin_password) if identity["user_id"] is None else None
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO web_sessions(token_hash,user_id,token_version,admin_password_hash,expires_at) "
            "VALUES (%s,%s,%s,%s,NOW()+INTERVAL '14 days')",
            (token_hash(token), identity["user_id"], identity.get("token_version", 0), emergency_hash),
        )
    return token


def get_web_session(token: str, admin_password: str) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT s.user_id,u.email,u.role,u.workspace_id,u.ui_language,u.token_version "
            "FROM web_sessions s LEFT JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>NOW() "
            "AND ((u.is_active AND u.deleted_at IS NULL AND u.token_version=s.token_version) "
            "OR (s.user_id IS NULL AND %s AND s.admin_password_hash=%s))",
            (token_hash(token), bool(admin_password), _admin_fingerprint(admin_password)),
        )
        identity = cursor.fetchone()
        if identity and identity["user_id"] is None:
            cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
            identity = {"user_id": None, "email": "shared-admin", "role": "admin",
                        "workspace_id": cursor.fetchone()["id"], "ui_language": "en"}
    return dict(identity) if identity else None


def revoke_web_session(token: str) -> None:
    with db() as connection:
        connection.cursor().execute(
            "UPDATE web_sessions SET revoked_at=NOW() WHERE token_hash=%s AND revoked_at IS NULL",
            (token_hash(token),),
        )
