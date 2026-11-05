"""Refresh browser identity from a live server-side session before route dispatch."""
from starlette.concurrency import run_in_threadpool

from gcrm.api.csrf import csrf_token
from gcrm.tools.db_web_sessions import get_web_session


async def refresh_browser_session(request, admin_password: str) -> dict | None:
    token = request.session.get("session_id")
    identity = await run_in_threadpool(get_web_session, token, admin_password) if token else None
    if identity:
        request.session.update(identity)
    else:
        for key in ("role", "user_id", "email", "workspace_id", "token_version", "session_id"):
            request.session.pop(key, None)
    request.state.browser_authenticated = identity is not None
    csrf_token(request)
    return identity
