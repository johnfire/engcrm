from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os

router = APIRouter()

UI_DIR = Path(__file__).parent.parent / "ui"
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SPECTATOR_PASSWORD = os.environ.get("SPECTATOR_PASSWORD", "")


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


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_role(request):
        return RedirectResponse(url="/approvals/")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...)):
    if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
        request.session["role"] = "admin"
        return RedirectResponse(url="/approvals/", status_code=303)
    if SPECTATOR_PASSWORD and password == SPECTATOR_PASSWORD:
        request.session["role"] = "spectator"
        return RedirectResponse(url="/approvals/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid password"}, status_code=401
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
