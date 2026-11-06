"""Password-reauthenticated, CSRF-protected authenticator settings."""
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_login
from gcrm.api.rate_limit import rate_limit_auth
from gcrm.api.templates import templates
from gcrm.api.totp import build_totp_uri
from gcrm.i18n import DEFAULT_LANGUAGE
from gcrm.i18n import translate as t
from gcrm.tools.db_mfa import begin_mfa_setup, change_mfa, enable_mfa
from gcrm.tools.db_users import get_user_by_email

router = APIRouter(prefix="/settings/two-factor", dependencies=[Depends(require_login)])


def _account(request: Request) -> dict:
    if request.session.get("user_id") is None:
        raise HTTPException(400, "Use an individual account to configure two-factor authentication")
    user = get_user_by_email(request.session["email"])
    if not user or user["id"] != request.session["user_id"]:
        raise HTTPException(401, "Account unavailable")
    return user


def _page(request: Request, user: dict, **context):
    response = templates.TemplateResponse(
        "two_factor.html", {"request": request, "mfa_enabled": user["mfa_enabled"], **context},
        status_code=400 if context.get("error") else 200,
    )
    response.headers["Content-Security-Policy"] = (
        f"default-src 'none'; script-src 'nonce-{request.state.csp_nonce}'; style-src 'self'; font-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@router.get("", response_class=HTMLResponse)
def settings(request: Request):
    return _page(request, _account(request))


@router.post("/{action}", response_class=HTMLResponse)
def update(request: Request, action: Literal["start", "enable", "disable", "recovery"],
           current_password: str = Form(...), mfa_code: str = Form(""),
           _throttle: None = Depends(rate_limit_auth)):
    user = _account(request)
    if action == "start":
        secret = begin_mfa_setup(user["id"], current_password)
        if secret:
            return _page(request, user, setup_secret=secret, setup_uri=build_totp_uri(secret, user["email"]))
        codes = None
    elif action == "enable":
        codes = enable_mfa(user["id"], current_password, mfa_code)
    else:
        codes = change_mfa(user["id"], current_password, mfa_code, disable=action == "disable")
    if codes is None:
        language = request.session.get("ui_language", DEFAULT_LANGUAGE)
        return _page(request, user, error=t("mfa.failed", language))
    language = request.session.get("ui_language", DEFAULT_LANGUAGE)
    request.session.clear()
    request.session["ui_language"] = language
    return _page(request, user, recovery_codes=codes, finished=True, disabled=action == "disable")
