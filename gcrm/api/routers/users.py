"""Admin-only web page to manage user accounts (email + bcrypt password).

A UI over the same db helpers as scripts/manage_users.py. Lets you create the
first real accounts and then retire the shared ADMIN_PASSWORD break-glass.
"""
import secrets
import string

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_admin
from gcrm.api.security import hash_password
from gcrm.api.templates import templates
from gcrm.i18n import DEFAULT_LANGUAGE
from gcrm.i18n import translate as t
from gcrm.tools.db import (
    create_user,
    get_user_by_email,
    list_users,
    set_user_active,
    set_user_password,
)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])

ROLES = ["admin", "spectator"]


def _lang(request: Request) -> str:
    return request.session.get("ui_language", DEFAULT_LANGUAGE)


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _flash(request: Request, msg: str = "", pw: str = "", error: str = "") -> None:
    request.session["user_flash"] = {"msg": msg, "pw": pw, "error": error}


@router.get("/", response_class=HTMLResponse)
def users_page(request: Request):
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": list_users(),
        "roles": ROLES,
        "flash": request.session.pop("user_flash", None),
    })


@router.post("/add")
def add_user(
    request: Request,
    email: str = Form(...),
    name: str = Form(""),
    role: str = Form("admin"),
    password: str = Form(""),
):
    email = email.strip().lower()
    role = role if role in ROLES else "admin"
    lang = _lang(request)
    if not email:
        _flash(request, error=t("users.emailRequired", lang))
        return RedirectResponse("/users/", status_code=303)
    if get_user_by_email(email):
        _flash(request, error=t("users.emailAlreadyExists", lang, email=email))
        return RedirectResponse("/users/", status_code=303)
    pw = password.strip() or _generate_password()
    try:
        create_user(email, hash_password(pw), role=role, name=name.strip())
    except Exception as error:  # surface DB errors instead of a 500
        _flash(request, error=t("users.couldNotCreate", lang, error=str(error)))
        return RedirectResponse("/users/", status_code=303)
    # Show the password once only when we generated it (admin typed their own → don't echo).
    _flash(request, msg=t("users.created", lang, email=email, role=role), pw="" if password.strip() else pw)
    return RedirectResponse("/users/", status_code=303)


@router.post("/passwd")
def reset_password(request: Request, email: str = Form(...), password: str = Form("")):
    email = email.strip().lower()
    lang = _lang(request)
    pw = password.strip() or _generate_password()
    if not set_user_password(email, hash_password(pw)):
        _flash(request, error=t("users.noSuchUser", lang, email=email))
    else:
        _flash(request, msg=t("users.passwordResetFor", lang, email=email), pw="" if password.strip() else pw)
    return RedirectResponse("/users/", status_code=303)


@router.post("/active")
def toggle_active(request: Request, email: str = Form(...), active: str = Form(...)):
    email = email.strip().lower()
    lang = _lang(request)
    want_active = active == "1"
    me = (request.session.get("email") or "").strip().lower()
    if me == email and not want_active:
        _flash(request, error=t("users.cantDisableSelf", lang))
        return RedirectResponse("/users/", status_code=303)
    if not set_user_active(email, want_active):
        _flash(request, error=t("users.noSuchUser", lang, email=email))
    else:
        key = "users.enabledFlash" if want_active else "users.disabledFlash"
        _flash(request, msg=t(key, lang, email=email))
    return RedirectResponse("/users/", status_code=303)
