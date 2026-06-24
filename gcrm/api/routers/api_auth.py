"""Mobile auth — exchange engcrm account credentials (email + password) for a
bearer JWT. Reuses the same per-user authentication as the web login."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import create_token
from gcrm.api.auth import authenticate
from gcrm.api.rate_limit import rate_limit_auth
from gcrm.tools.db import get_user_by_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["mobile-auth"])


class TokenRequest(BaseModel):
    email: str = ""
    password: str


class TokenResponse(BaseModel):
    token: str
    role: str


@router.post("/token", response_model=TokenResponse)
def get_token(body: TokenRequest, _throttle: None = Depends(rate_limit_auth)) -> TokenResponse:
    user = None
    if body.email:
        try:
            user = get_user_by_email(body.email)
        except Exception as error:  # tolerate DB hiccup so break-glass still works
            logger.warning("mobile auth user lookup failed: %s", error)
    payload = authenticate(body.email, body.password, user)
    if payload:
        return TokenResponse(
            token=create_token(
                payload["role"],
                user_id=payload.get("user_id"),
                token_version=payload.get("token_version", 0),
            ),
            role=payload["role"],
        )
    raise HTTPException(status_code=401, detail="Invalid email or password")
