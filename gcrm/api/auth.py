import hmac
import logging
import os
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.rate_limit import rate_limit_auth
from gcrm.api.security import hash_password, verify_password
from gcrm.api.templates import templates
from gcrm.audit_context import set_audit_context
from gcrm.config import APP_PUBLIC_URL
from gcrm.i18n import DEFAULT_LANGUAGE
from gcrm.i18n import translate as t
from gcrm.tools.db import get_user_by_email, touch_user_login
from gcrm.tools.db_account_lifecycle import (
    consume_password_reset_token,
    create_password_reset_token,
    password_reset_token_valid,
)
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_help import has_completed_help_tour
from gcrm.tools.db_users import set_user_password_by_id
from gcrm.tools.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter()

# Transitional break-glass: a shared admin password from the environment, honoured
# until real user accounts exist. Unset ADMIN_PASSWORD in the deployed .env to
# disable it once accounts are created (see scripts/manage_users.py).
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def get_role(request: Request) -> str | None:
    return request.session.get("role")


def require_login(request: Request) -> str:
    role = get_role(request)
    if not role:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    actor = request.session.get("email") or "shared-admin"
    set_audit_context(actor, "user", request.state.correlation_id)
    return role


def require_admin(request: Request) -> str:
    role = require_login(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return role


def authenticate(email: str, password: str, user: dict | None) -> dict | None:
    """
    Core login decision — pure (no DB, no request) so it is unit-testable.
    Returns a session payload on success, otherwise None.
    """
    if user and user.get("is_active") and verify_password(password, user["password_hash"]):
        return {
            "role": user["role"], "user_id": user["id"], "email": user["email"],
            "token_version": user.get("token_version", 0),
            "workspace_id": user.get("workspace_id"),
            "ui_language": user.get("ui_language") or DEFAULT_LANGUAGE,
        }
    # Break-glass: shared env admin password (transitional; email ignored).
    # Constant-time compare so a wrong password can't be inferred from timing.
    if ADMIN_PASSWORD and hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        return {"role": "admin", "user_id": None, "email": "shared-admin", "workspace_id": None}
    return None


def _lookup_user(email: str) -> dict | None:
    """Fetch a user, tolerating DB failure so break-glass still works if the DB is down."""
    if not email:
        return None
    try:
        return get_user_by_email(email)
    except Exception as error:  # login must not 500 on a DB hiccup
        logger.warning("user lookup failed during login (%s); break-glass only", error)
        return None


def request_password_reset(email: str) -> None:
    """
    Email a reset link if `email` matches an active account. Always returns
    normally regardless of whether a match was found or the email send
    succeeded — the caller must show the same generic message either way, so a
    reset request can never be used to enumerate which emails have accounts.
    """
    user = _lookup_user((email or "").strip().lower())
    if not user or not user.get("is_active"):
        return
    token = secrets.token_urlsafe(32)
    create_password_reset_token(user["id"], token)
    link = f"{APP_PUBLIC_URL}/reset-password?token={token}"
    send_email(
        user["email"],
        "Reset your EngCRM password",
        "Someone requested a password reset for this EngCRM account.\n\n"
        f"Reset it here (valid for 1 hour): {link}\n\n"
        "If you didn't request this, you can safely ignore this email — "
        "your password will not change.",
    )


def complete_password_reset(token: str, new_password: str) -> bool:
    """Consume a reset token and set the new password. False if the token is
    missing/expired/already used, or the password fails the length policy."""
    if len(new_password) < 12:
        return False
    user_id = consume_password_reset_token(token)
    if user_id is None:
        return False
    return set_user_password_by_id(user_id, hash_password(new_password))


def _post_login_destination(user_id: int | None) -> str:
    """Start an account's guided workflow once without blocking login on DB trouble."""
    if user_id is None:
        return "/approvals/"
    try:
        return "/approvals/" if has_completed_help_tour(user_id) else "/help/?tour=1"
    except Exception as error:
        logger.warning("help tour lookup failed after login: %s", error)
        return "/approvals/"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_role(request):
        return RedirectResponse(url="/approvals/")
    reset_success = request.query_params.get("reset") == "success"
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None, "reset_success": reset_success},
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(""), password: str = Form(...), _throttle: None = Depends(rate_limit_auth)):
    payload = authenticate(email, password, _lookup_user(email))
    if payload:
        request.session.update(payload)
        if payload["user_id"] is not None:
            try:
                touch_user_login(payload["user_id"])
            except Exception as error:  # a failed timestamp update must not block login
                logger.warning("touch_user_login failed: %s", error)
        log_audit(payload["email"], "user", "auth.login", f"user:{payload['email']}", "success", request.state.correlation_id)
        return RedirectResponse(url=_post_login_destination(payload["user_id"]), status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": t("login.invalidCredentials", request.session.get("ui_language", DEFAULT_LANGUAGE)),
            "reset_success": False,
        },
        status_code=401,
    )


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request, "sent": False})


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_submit(
    request: Request,
    email: str = Form(""),
    _throttle: None = Depends(rate_limit_auth),
):
    request_password_reset(email)
    return templates.TemplateResponse("forgot_password.html", {"request": request, "sent": True})


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str = ""):
    valid = bool(token) and password_reset_token_valid(token)
    return templates.TemplateResponse(
        "reset_password.html", {"request": request, "token": token, "valid": valid, "error": None},
    )


@router.post("/reset-password", response_class=HTMLResponse)
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    _throttle: None = Depends(rate_limit_auth),
):
    if complete_password_reset(token, new_password):
        return RedirectResponse(url="/login?reset=success", status_code=303)
    return templates.TemplateResponse(
        "reset_password.html",
        {
            "request": request, "token": token, "valid": True,
            "error": t("resetPassword.errorGeneric", request.session.get("ui_language", DEFAULT_LANGUAGE)),
        },
        status_code=400,
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
