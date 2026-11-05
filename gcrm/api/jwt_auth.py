"""Bearer-JWT auth for the mobile JSON API (HS256, 30-day lifetime via
TOKEN_EXPIRY_HOURS). Separate from the cookie/session auth used by the
server-rendered web UI.

Tokens minted for a real user account carry uid + ver (the user's token
version). On each request the version is checked against the user's current
version (and active flag) in the DB, so deactivating a user or resetting their
password immediately revokes their outstanding tokens. Tokens with no uid (the
transitional shared break-glass admin) are not version-checked.
"""
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from gcrm.audit_context import set_audit_context
from gcrm.config import JWT_SECRET, TOKEN_EXPIRY_HOURS
from gcrm.tools.db import get_user_token_version
from gcrm.tools.db_users import get_user_by_id
from gcrm.workspace_context import require_workspace_scope, set_workspace_id

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

_bearer = HTTPBearer()


def create_token(
    role: str,
    user_id: int | None = None,
    token_version: int = 0,
    secret: str = JWT_SECRET,
) -> str:
    payload = {
        "sub": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    if user_id is not None:
        payload["uid"] = user_id
        payload["ver"] = token_version
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token_payload(token: str, secret: str = JWT_SECRET) -> dict:
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    if not payload.get("sub"):
        raise jwt.InvalidTokenError("Missing sub claim")
    return payload


def decode_token(token: str, secret: str = JWT_SECRET) -> str:
    """Return the caller's role (the sub claim)."""
    return decode_token_payload(token, secret)["sub"]


def _token_version_ok(user_id: int, token_version) -> bool:
    """True if the token's version matches the user's current (active) version.

    Authentication storage failures refuse access rather than guessing that a
    credential is still valid."""
    try:
        current = get_user_token_version(user_id)
    except Exception as error:
        logger.warning("token version check unavailable: %s", error)
        raise HTTPException(503, "Authentication temporarily unavailable") from error
    return current is not None and current == token_version


def _validated_payload(credentials: HTTPAuthorizationCredentials) -> dict:
    """Decode and revoke-check a bearer credential without request concerns."""
    try:
        payload = decode_token_payload(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("uid")
    if user_id is not None and not _token_version_ok(user_id, payload.get("ver")):
        raise HTTPException(status_code=401, detail="Token revoked")
    return payload


async def establish_jwt_workspace(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """Run in the request's async context so handlers inherit the verified scope."""
    payload = await run_in_threadpool(_validated_payload, credentials)
    user_id = payload.get("uid")
    if user_id is not None:
        try:
            user = await run_in_threadpool(get_user_by_id, user_id)
        except Exception as error:
            logger.warning("account lookup unavailable: %s", error)
            raise HTTPException(503, "Authentication temporarily unavailable") from error
        if not user or not user["is_active"] or user["token_version"] != payload.get("ver"):
            raise HTTPException(401, "Token revoked")
        if user.get("workspace_id") is None:
            raise HTTPException(403, "Workspace required")
        set_workspace_id(user["workspace_id"])
        payload = {**payload, "sub": user["role"]}
    require_workspace_scope()
    actor = f"user:{user_id}" if user_id is not None else "shared-admin"
    set_audit_context(actor, "user", request.state.correlation_id)
    return payload


def require_jwt_payload(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    scope: dict = Depends(establish_jwt_workspace),
) -> dict:
    """FastAPI dependency: returns the validated token payload, or 401."""
    payload = scope if isinstance(scope, dict) else _validated_payload(credentials)
    user_id = payload.get("uid")
    actor = f"user:{user_id}" if user_id is not None else "shared-admin"
    set_audit_context(actor, "user", request.state.correlation_id)
    return payload


def require_jwt(credentials: HTTPAuthorizationCredentials = Security(_bearer), scope: dict = Depends(establish_jwt_workspace)) -> str:
    """FastAPI dependency: returns the caller's role, or 401."""
    return (scope if isinstance(scope, dict) else _validated_payload(credentials))["sub"]


def require_jwt_admin(payload: dict = Depends(require_jwt_payload)) -> str:
    """FastAPI dependency: like require_jwt but requires the admin role (403 otherwise)."""
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload["sub"]
