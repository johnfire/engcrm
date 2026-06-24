"""Bearer-JWT auth for the mobile JSON API (HS256, 24h). Separate from the
cookie/session auth used by the server-rendered web UI."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gcrm.config import JWT_SECRET

ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

_bearer = HTTPBearer()


def create_token(role: str, secret: str = JWT_SECRET) -> str:
    payload = {
        "sub": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str = JWT_SECRET) -> str:
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    role = payload.get("sub")
    if not role:
        raise jwt.InvalidTokenError("Missing sub claim")
    return role


def require_jwt(credentials: HTTPAuthorizationCredentials = Security(_bearer)) -> str:
    """FastAPI dependency: returns the caller's role, or 401."""
    try:
        return decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_jwt_admin(role: str = Depends(require_jwt)) -> str:
    """FastAPI dependency: like require_jwt but requires the admin role (403 otherwise)."""
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return role
