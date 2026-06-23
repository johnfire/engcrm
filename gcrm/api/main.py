from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
import os

from gcrm.api.routers import approval, activity, contacts, people, research, inbox, marketing, drafts, users
from gcrm.api.routers import (
    api_auth, api_push, api_approvals, api_inbox,
    api_contacts, api_activity, api_research, api_cards,
)
from gcrm.api import auth

app = FastAPI(title="EngCRM Supervisor", docs_url=None, redoc_url=None)

# CORS for the mobile app — it authenticates with a bearer JWT (no cookies),
# so allowing all origins is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me-in-production")
# Secure-flag the session cookie in production (HTTPS). Leave false for local
# HTTP dev, or the browser won't send the cookie back. Set SESSION_COOKIE_SECURE=true
# in the deployed .env.
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=SESSION_COOKIE_SECURE,
)

UI_DIR = Path(__file__).parent.parent / "ui"
app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))

app.include_router(auth.router)
app.include_router(approval.router)
app.include_router(activity.router)
app.include_router(contacts.router)
app.include_router(people.router)
app.include_router(research.router)
app.include_router(inbox.router)
app.include_router(marketing.router)
app.include_router(drafts.router)
app.include_router(users.router)

# Mobile JSON API (bearer-JWT, under /api/*)
app.include_router(api_auth.router)
app.include_router(api_push.router)
app.include_router(api_approvals.router)
app.include_router(api_inbox.router)
app.include_router(api_contacts.router)
app.include_router(api_activity.router)
app.include_router(api_research.router)
app.include_router(api_cards.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse(url="/approvals/")


def run():
    import uvicorn
    from gcrm.config import HOST, PORT
    uvicorn.run("gcrm.api.main:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    run()
