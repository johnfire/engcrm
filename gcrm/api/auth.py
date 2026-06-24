from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import hmac
import logging
import os

from gcrm.tools.db import get_user_by_email, touch_user_login
from gcrm.api.security import verify_password
from gcrm.api.rate_limit import rate_limit_auth

logger = logging.getLogger(__name__)
router = APIRouter()

UI_DIR = Path(__file__).parent.parent / "ui"
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))

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
        }
    # Break-glass: shared env admin password (transitional; email ignored).
    # Constant-time compare so a wrong password can't be inferred from timing.
    if ADMIN_PASSWORD and hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        return {"role": "admin", "user_id": None, "email": "shared-admin"}
    return None


def _lookup_user(email: str) -> dict | None:
    """Fetch a user, tolerating DB failure so break-glass still works if the DB is down."""
    if not email:
        return None
    try:
        return get_user_by_email(email)
    except Exception as e:  # login must not 500 on a DB hiccup
        logger.warning("user lookup failed during login (%s); break-glass only", e)
        return None


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_role(request):
        return RedirectResponse(url="/approvals/")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(""), password: str = Form(...), _throttle: None = Depends(rate_limit_auth)):
    payload = authenticate(email, password, _lookup_user(email))
    if payload:
        request.session.update(payload)
        if payload["user_id"] is not None:
            try:
                touch_user_login(payload["user_id"])
            except Exception as e:  # a failed timestamp update must not block login
                logger.warning("touch_user_login failed: %s", e)
        return RedirectResponse(url="/approvals/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid email or password"},
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
