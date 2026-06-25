from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from gcrm.api.routers import approval, activity, contacts, people, research, inbox, marketing, drafts, users
from gcrm.api.routers import (
    api_auth, api_push, api_approvals, api_inbox,
    api_contacts, api_activity, api_research, api_cards, api_voice, api_people,
    api_pipeline, api_recon,
)
from gcrm.api import auth
from gcrm.config import SESSION_SECRET, SESSION_COOKIE_SECURE

app = FastAPI(title="EngCRM Supervisor", docs_url=None, redoc_url=None)

# CORS for the mobile app — it authenticates with a bearer JWT (no cookies),
# so allowing all origins is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Session secret + cookie-secure flag are resolved in gcrm.config (fail-closed in
# production). https_only must be true when the app is served over HTTPS.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=SESSION_COOKIE_SECURE,
    same_site="lax",
)

UI_DIR = Path(__file__).parent.parent / "ui"
app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")

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
app.include_router(api_voice.router)
app.include_router(api_people.router)
app.include_router(api_pipeline.router)
app.include_router(api_recon.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse(url="/approvals/")


def run():
    import uvicorn
    from gcrm.config import HOST, PORT
    uvicorn.run("gcrm.api.main:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    run()
