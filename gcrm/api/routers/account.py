"""Invite-only registration and self-service password settings."""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_login
from gcrm.api.security import hash_password, verify_password
from gcrm.api.templates import templates
from gcrm.tools.db_account_lifecycle import accept_invitation
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_users import get_user_by_email, set_user_password

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account"])


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    """Show the invite-only registration form."""
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@router.post("/signup", response_class=HTMLResponse)
def signup_submit(
    request: Request,
    email: str = Form(...),
    name: str = Form(""),
    password: str = Form(...),
    invitation_token: str = Form(...),
):
    """Create an account only after atomically consuming its invitation."""
    normalized_email = email.strip().lower()
    if len(password) < 12:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "Use a password with at least 12 characters."},
            status_code=400,
        )
    try:
        user_id = accept_invitation(normalized_email, hash_password(password), invitation_token, name.strip())
    except Exception as error:
        logger.warning("signup failed for invited account: %s", error)
        user_id = None
    if user_id is None:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "The invitation is invalid, expired, or already used."},
            status_code=400,
        )
    log_audit(str(user_id), "user", "account.signup", f"user:{user_id}", "created", request.state.correlation_id)
    return RedirectResponse("/login", status_code=303)


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def settings_page(request: Request):
    """Show the signed-in user's account settings."""
    return templates.TemplateResponse("settings.html", {"request": request, "message": None, "error": None})


@router.post("/settings/password", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    """Require the current password before updating and revoking account tokens."""
    email = request.session.get("email", "")
    user = get_user_by_email(email)
    if not user or not verify_password(current_password, user["password_hash"]):
        return templates.TemplateResponse(
            "settings.html", {"request": request, "message": None, "error": "Current password is incorrect."},
            status_code=400,
        )
    if len(new_password) < 12:
        return templates.TemplateResponse(
            "settings.html", {"request": request, "message": None, "error": "Use a password with at least 12 characters."},
            status_code=400,
        )
    set_user_password(email, hash_password(new_password))
    log_audit(email, "user", "account.password_changed", f"user:{user['id']}", "success", request.state.correlation_id)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
