"""Mobile auth — exchange engcrm account credentials (email + password) for a
bearer JWT. Reuses the same per-user authentication as the web login."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.auth import authenticate, request_password_reset
from gcrm.api.jwt_auth import create_token
from gcrm.api.rate_limit import rate_limit_auth
from gcrm.tools.db import get_user_by_email
from gcrm.tools.db_audit import log_audit

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
        log_audit(
            payload["email"],
            "user",
            "auth.mobile_token_issued",
            f"user:{payload['email']}",
            "success",
        )
        return TokenResponse(
            token=create_token(
                payload["role"],
                user_id=payload.get("user_id"),
                token_version=payload.get("token_version", 0),
            ),
            role=payload["role"],
        )
    raise HTTPException(status_code=401, detail="Invalid email or password")


class ResetRequest(BaseModel):
    email: str = ""


@router.post("/reset-request")
def reset_request(body: ResetRequest, _throttle: None = Depends(rate_limit_auth)) -> dict:
    """
    Request a password-reset email. Actual reset happens on the web
    (/reset-password) — the emailed link opens fine in the phone's browser, so
    the app doesn't need its own token-consuming screen or deep-link handling.

    Always returns {ok: true} — never reveals whether the email matched an
    account, same as the web /forgot-password form.
    """
    request_password_reset(body.email)
    return {"ok": True}
