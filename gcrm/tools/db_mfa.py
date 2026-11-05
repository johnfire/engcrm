"""Locked, account-bound authenticator enrollment and one-use factor checks."""
import hashlib
import logging
import secrets
from datetime import datetime, timezone

from gcrm.api.security import decrypt_totp_secret, encrypt_totp_secret, verify_password
from gcrm.api.totp import generate_totp_secret, matching_totp_counter
from gcrm.audit_context import current_audit_context
from gcrm.config import ACCOUNT_ENCRYPTION_KEY
from gcrm.db.connection import db

logger = logging.getLogger(__name__)


def _audit_change(cursor, user: dict, action: str) -> None:
    context = current_audit_context()
    cursor.execute(
        """INSERT INTO audit_log(workspace_id,actor,actor_type,action,target,outcome,correlation_id)
        VALUES (%s,%s,'user',%s,%s,'success',%s)""",
        (user["workspace_id"], user["email"], action, f"user:{user['id']}",
         context.correlation_id if context else None),
    )


def _recovery_hash(code: str) -> str:
    return hashlib.sha256(code.strip().replace("-", "").lower().encode()).hexdigest()


def _new_recovery_codes() -> list[str]:
    return [secrets.token_hex(16) for _ in range(10)]


def _locked_user(cursor, user_id: int) -> dict | None:
    cursor.execute("SELECT * FROM users WHERE id=%s AND is_active=TRUE FOR UPDATE", (user_id,))
    return cursor.fetchone()


def _is_blocked(user: dict) -> bool:
    return bool(user["mfa_blocked_until"] and user["mfa_blocked_until"] > datetime.now(timezone.utc))


def _record_failure(cursor, user_id: int) -> None:
    cursor.execute(
        """UPDATE users SET mfa_failed_attempts=mfa_failed_attempts+1,
        mfa_blocked_until=CASE WHEN mfa_failed_attempts>=9 THEN NOW()+INTERVAL '5 minutes'
        ELSE NULL END WHERE id=%s""", (user_id,),
    )


def _consume_factor(cursor, user: dict, code: str) -> bool:
    if _is_blocked(user):
        return False
    if _consume_totp(cursor, user, code):
        return True
    code_hash = _recovery_hash(code)
    if code_hash in user["mfa_recovery_hashes"]:
        cursor.execute("UPDATE users SET mfa_recovery_hashes=array_remove(mfa_recovery_hashes,%s), "
                       "mfa_failed_attempts=0,mfa_blocked_until=NULL WHERE id=%s", (code_hash, user["id"]))
        _audit_change(cursor, user, "account.mfa_recovery_used")
        return True
    _record_failure(cursor, user["id"])
    return False


def _consume_totp(cursor, user: dict, code: str) -> bool:
    try:
        secret = decrypt_totp_secret(user["mfa_secret_encrypted"], ACCOUNT_ENCRYPTION_KEY)
        counter = matching_totp_counter(secret, code.strip())
    except Exception:
        logger.warning("MFA seed unavailable for user:%s", user["id"])
        return False
    if counter is None or counter <= user["mfa_last_counter"]:
        return False
    cursor.execute("UPDATE users SET mfa_last_counter=%s,mfa_failed_attempts=0,mfa_blocked_until=NULL "
                   "WHERE id=%s", (counter, user["id"]))
    return True


def verify_login_factor(user_id: int, code: str, token_version: int) -> bool:
    """Consume a factor under the user lock; stale password proofs cannot log in."""
    with db() as connection:
        cursor = connection.cursor()
        user = _locked_user(cursor, user_id)
        if not user or user["token_version"] != token_version:
            return False
        return _consume_factor(cursor, user, code) if user["mfa_enabled"] else True


def begin_mfa_setup(user_id: int, password: str) -> str | None:
    """Store a ten-minute encrypted pending seed after password reauthentication."""
    with db() as connection:
        cursor = connection.cursor()
        user = _locked_user(cursor, user_id)
        if not user or user["mfa_enabled"] or not verify_password(password, user["password_hash"]):
            return None
        secret = generate_totp_secret()
        cursor.execute("UPDATE users SET mfa_pending_secret=%s, "
                       "mfa_pending_expires_at=NOW()+INTERVAL '10 minutes' WHERE id=%s",
                       (encrypt_totp_secret(secret, ACCOUNT_ENCRYPTION_KEY), user_id))
        _audit_change(cursor, user, "account.mfa_setup_started")
        return secret


def enable_mfa(user_id: int, password: str, code: str) -> list[str] | None:
    """Prove the pending seed, activate it, and revoke all existing credentials."""
    with db() as connection:
        cursor = connection.cursor()
        user = _locked_user(cursor, user_id)
        if not _can_enable(user, password):
            return None
        try:
            secret = decrypt_totp_secret(user["mfa_pending_secret"], ACCOUNT_ENCRYPTION_KEY)
            counter = matching_totp_counter(secret, code.strip())
        except Exception:
            counter = None
        if counter is None:
            _record_failure(cursor, user_id)
            return None
        codes = _new_recovery_codes()
        cursor.execute(
            """UPDATE users SET mfa_enabled=TRUE,mfa_secret_encrypted=mfa_pending_secret,
            mfa_pending_secret=NULL,mfa_pending_expires_at=NULL,mfa_last_counter=%s,
            mfa_recovery_hashes=%s,mfa_failed_attempts=0,mfa_blocked_until=NULL,
            token_version=token_version+1 WHERE id=%s""",
            (counter, [_recovery_hash(code) for code in codes], user_id),
        )
        _audit_change(cursor, user, "account.mfa_enabled")
        return codes


def _can_enable(user: dict | None, password: str) -> bool:
    return bool(user and not user["mfa_enabled"] and not _is_blocked(user)
                and user["mfa_pending_secret"] and user["mfa_pending_expires_at"]
                and user["mfa_pending_expires_at"] > datetime.now(timezone.utc)
                and verify_password(password, user["password_hash"]))


def change_mfa(user_id: int, password: str, code: str, *, disable: bool) -> list[str] | None:
    """Require both current factors before disabling or replacing recovery codes."""
    with db() as connection:
        cursor = connection.cursor()
        user = _locked_user(cursor, user_id)
        if not user or not user["mfa_enabled"] or not verify_password(password, user["password_hash"]):
            return None
        if not _consume_factor(cursor, user, code):
            return None
        codes = [] if disable else _new_recovery_codes()
        cursor.execute(
            """UPDATE users SET mfa_enabled=%s,mfa_secret_encrypted=%s,
            mfa_pending_secret=NULL,mfa_pending_expires_at=NULL,mfa_recovery_hashes=%s,
            token_version=token_version+1 WHERE id=%s""",
            (not disable, None if disable else user["mfa_secret_encrypted"],
             [_recovery_hash(code) for code in codes], user_id),
        )
        _audit_change(cursor, user, "account.mfa_disabled" if disable else "account.mfa_recovery_replaced")
        return codes
