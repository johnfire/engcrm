"""Bearer-JWT auth for the mobile JSON API (HS256, 24h). Separate from the
cookie/session auth used by the server-rendered web UI.

Tokens minted for a real user account carry uid + ver (the user's token
version). On each request the version is checked against the user's current
version (and active flag) in the DB, so deactivating a user or resetting their
password immediately revokes their outstanding tokens. Tokens with no uid (the
transitional shared break-glass admin) are not version-checked.
"""
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gcrm.config import JWT_SECRET
from gcrm.tools.db import get_user_token_version

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

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

    Fails OPEN on a DB error — consistent with the rest of the auth layer, and
    harmless because every protected endpoint needs the DB anyway, so a revoked
    token still can't do anything during an outage."""
    try:
        current = get_user_token_version(user_id)
    except Exception as error:
        logger.warning("token version check failed (allowing request): %s", error)
        return True
    return current is not None and current == token_version


def require_jwt(credentials: HTTPAuthorizationCredentials = Security(_bearer)) -> str:
    """FastAPI dependency: returns the caller's role, or 401."""
    try:
        payload = decode_token_payload(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("uid")
    if user_id is not None and not _token_version_ok(user_id, payload.get("ver")):
        raise HTTPException(status_code=401, detail="Token revoked")
    return payload["sub"]


def require_jwt_admin(role: str = Depends(require_jwt)) -> str:
    """FastAPI dependency: like require_jwt but requires the admin role (403 otherwise)."""
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return role
