import logging
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from gcrm.api import auth
from gcrm.api.routers import (
    account,
    activity,
    api_account,
    api_activity,
    api_approvals,
    api_auth,
    api_cards,
    api_contacts,
    api_help,
    api_inbox,
    api_people,
    api_pipeline,
    api_push,
    api_recon,
    api_research,
    api_signs,
    api_voice,
    approval,
    contacts,
    drafts,
    inbox,
    help,
    legal,
    marketing,
    people,
    research,
    users,
)
from gcrm.audit_context import CorrelationIdFilter, audit_scope
from gcrm.config import SESSION_COOKIE_SECURE, SESSION_SECRET
from gcrm.i18n import SUPPORTED_LANGUAGES
from gcrm.workspace_context import set_workspace_id

app = FastAPI(title="EngCRM Supervisor", docs_url=None, redoc_url=None)
for handler in logging.getLogger().handlers:
    handler.addFilter(CorrelationIdFilter())


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Attach a request ID to every HTTP response and downstream audit event.

    Also handles a `?lang=de`/`?lang=en` query param as a pre-login language
    toggle (login/forgot-password/reset-password/Impressum have no account
    yet to read a preference from). Any page can carry this param; a signed-
    in user's account-level preference (set on login) simply overwrites it
    the moment they authenticate.
    """
    correlation_id = request.headers.get("x-request-id") or uuid4().hex[:16]
    request.state.correlation_id = correlation_id
    session = request.session
    lang = request.query_params.get("lang")
    if lang in SUPPORTED_LANGUAGES:
        session["ui_language"] = lang
    workspace_id = session.get("workspace_id")
    set_workspace_id(workspace_id)
    actor = session.get("email") or "anonymous"
    with audit_scope(actor, "user", correlation_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response

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
app.include_router(legal.router)
app.include_router(account.router)
app.include_router(approval.router)
app.include_router(activity.router)
app.include_router(contacts.router)
app.include_router(people.router)
app.include_router(research.router)
app.include_router(inbox.router)
app.include_router(marketing.router)
app.include_router(drafts.router)
app.include_router(users.router)
app.include_router(help.router)

# Mobile JSON API (bearer-JWT, under /api/*)
app.include_router(api_auth.router)
app.include_router(api_account.router)
app.include_router(api_push.router)
app.include_router(api_approvals.router)
app.include_router(api_inbox.router)
app.include_router(api_contacts.router)
app.include_router(api_activity.router)
app.include_router(api_research.router)
app.include_router(api_cards.router)
app.include_router(api_signs.router)
app.include_router(api_voice.router)
app.include_router(api_people.router)
app.include_router(api_pipeline.router)
app.include_router(api_recon.router)
app.include_router(api_help.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse(url="/approvals/")


def run():
    import uvicorn

    from gcrm.config import HOST, PORT
    uvicorn.run("gcrm.api.main:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    run()
