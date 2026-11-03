"""The remote MCP connector: the field tools, reachable from Claude anywhere.

Mounted on the web app at /mcp (gcrm/api/main.py), so the existing HTTPS front door
serves it with no extra server setup. Plain request/response (stateless, JSON): no
streams for a proxy to buffer. Every request needs a token from gcrm/mcp/tokens.py
(`Authorization: Bearer engcrm_...`); a missing, wrong or revoked one gets 401 before any
tool runs, and each token is rate limited. Only the field tools are here: nothing that
sends email, runs agents or manages accounts (see the plan's tiers,
docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md).
"""
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import partial
from uuid import uuid4

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

from gcrm.api.rate_limit import FixedWindowRateLimiter
from gcrm.audit_context import audit_scope
from gcrm.mcp import field
from gcrm.mcp.field import FieldError, FieldUser
from gcrm.mcp.tokens import verify_token
from gcrm.workspace_context import set_workspace_id

logger = logging.getLogger(__name__)

_caller: ContextVar[FieldUser | None] = ContextVar("mcp_caller", default=None)
# A voice conversation makes a handful of calls a minute; this only stops a runaway.
_limiter = FixedWindowRateLimiter(max_attempts=120, window_seconds=60.0)

INSTRUCTIONS = """You are Chris's hands for EngCRM, his CRM, while he is out visiting businesses.
He talks; you save. Typical turn: where_am_i or businesses_here to see what is around him,
find_organization to check it is not already there, add_organization (pass the place_id,
address and coordinates businesses_here gave you), add_person for who he met, log_activity for
what happened, set_next_step or set_ratings when he says so. When two businesses could be the
one, ask him which. Every tool answers with "said": read it back to him, so a wrong match is
caught at once. If he says that was wrong, call undo_last. If a tool returns "error", say it
plainly and ask what he wants instead. Dates are typed like 28.10.2026."""

server = FastMCP(
    "engcrm-field",
    instructions=INSTRUCTIONS,
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    # DNS-rebinding protection guards servers on a user's own machine from web pages in
    # their browser. This endpoint is public on purpose and the bearer token guards it;
    # a Host check would only break behind the proxy.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _run(user: FieldUser, tool, args, kwargs) -> dict:
    """A field tool as the token's user, in their workspace, audit-logged as the
    connector. A refusal comes back as {"error": ...} for Claude to say."""
    set_workspace_id(user.workspace_id)
    with audit_scope(f"mcp:user:{user.user_id}", "mcp", f"mcp:{uuid4().hex[:16]}"):
        try:
            result = tool(user, *args, **kwargs)
        except FieldError as refusal:
            return {"error": str(refusal)}
    return result if isinstance(result, dict) else {"results": result}


async def _call(tool, *args, **kwargs) -> dict:
    """Run a tool on a worker thread: its database and Google calls block, and the web
    app's other requests share this event loop."""
    user = _caller.get()
    if user is None:  # unreachable behind BearerAuth; kept so a wiring slip fails closed
        return {"error": "Not signed in."}
    return await anyio.to_thread.run_sync(partial(_run, user, tool, args, kwargs))


@server.tool()
async def where_am_i() -> dict:
    """Chris's current position from his phone's Field mode, with its age and town."""
    return await _call(field.where_am_i)


@server.tool()
async def businesses_here(radius_m: int = 60) -> dict:
    """The businesses within radius_m metres of Chris, nearest first, each marked
    in_engcrm when it is already an organization."""
    return await _call(field.businesses_here, radius_m)


@server.tool()
async def find_organization(query: str) -> dict:
    """Organizations in EngCRM whose name or town contains query."""
    return await _call(field.find_organization, query)


@server.tool()
async def add_organization(name: str, city: str = "", address: str = "", type: str = "", place_id: str = "",
                     latitude: float | None = None, longitude: float | None = None, notes: str = "",
                     country: str = "DE") -> dict:
    """Save a business as a new organization. An existing one is reported, not duplicated."""
    return await _call(field.add_organization, name, city=city, address=address, type=type, place_id=place_id,
                 latitude=latitude, longitude=longitude, notes=notes, country=country)


@server.tool()
async def add_person(organization_id: int, name: str, title: str = "", email: str = "", phone: str = "",
               notes: str = "", met_at: str = "") -> dict:
    """Save a person Chris met at an organization."""
    return await _call(field.add_person, organization_id, name, title=title, email=email, phone=phone,
                 notes=notes, met_at=met_at)


@server.tool()
async def log_activity(note: str, organization_id: int | None = None, person_id: int | None = None,
                 kind: str = "drop_in", minutes: int | None = None, attitude: list[str] | None = None,
                 my_read: list[str] | None = None, materials_left: str = "", follow_up_promised: str = "",
                 follow_up_date: str = "", offer: str | None = None, occurred_on: str = "") -> dict:
    """Log what happened, on one organization or one person. kind: drop_in, meeting, phone,
    video, email, post_mail, note. attitude (how they seemed to feel about Chris): warm,
    neutral, cold, skeptical. my_read (how they seemed to him): trustworthy, straightforward,
    cant_tell, holding_back, story_doesnt_add_up, not_truthful, indecisive, confused, nh, cf.
    materials_left, follow_up_promised, follow_up_date and occurred_on are for organizations."""
    return await _call(field.log_activity, note, organization_id=organization_id, person_id=person_id, kind=kind,
                 minutes=minutes, attitude=attitude, my_read=my_read, materials_left=materials_left,
                 follow_up_promised=follow_up_promised, follow_up_date=follow_up_date, offer=offer,
                 occurred_on=occurred_on)


@server.tool()
async def set_next_step(step: str, due: str = "", organization_id: int | None = None, person_id: int | None = None,
                  offer: str = "") -> dict:
    """What happens next on the deal of one organization or person; a blank step clears it."""
    return await _call(field.set_next_step, step, due=due, organization_id=organization_id, person_id=person_id,
                 offer=offer)


@server.tool()
async def set_ratings(organization_id: int | None = None, person_id: int | None = None, priority: int | None = None,
                short_term_value: int | None = None, long_term_value: int | None = None) -> dict:
    """Chris's private ratings. priority: 1 best .. 6 forget it (people 1..5).
    short_term_value / long_term_value: 3 high, 2 medium, 1 low, 0 zero."""
    return await _call(field.set_ratings, organization_id=organization_id, person_id=person_id, priority=priority,
                 short_term_value=short_term_value, long_term_value=long_term_value)


@server.tool()
async def undo_last() -> dict:
    """Take back the newest thing saved through this connector."""
    return await _call(field.undo_last)


def _refuse(status: int, message: str):
    body = json.dumps({"error": message}).encode()
    return {"type": "http.response.start", "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]}, \
        {"type": "http.response.body", "body": body}


class BearerAuth:
    """ASGI wrapper: no tool runs without a live token; the token's user is the caller."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        account = await anyio.to_thread.run_sync(verify_token, token) if token else None
        if account is None:
            for message in _refuse(401, "A valid EngCRM connector token is required."):
                await send(message)
            return
        if not _limiter.allow(f"mcp-token:{account['token_id']}"):
            for message in _refuse(429, "Too many requests; wait a minute."):
                await send(message)
            return
        reset = _caller.set(FieldUser(account["user_id"], account["workspace_id"]))
        try:
            await self.app(scope, receive, send)
        finally:
            _caller.reset(reset)


class _Endpoint:
    """Hands each request to the session manager of the running app. The SDK's manager
    can be run only once, so `running()` makes a fresh one each time the web app starts
    (once in production; once per test client in tests)."""

    def __init__(self):
        self.manager: StreamableHTTPSessionManager | None = None

    async def __call__(self, scope, receive, send):
        if self.manager is None:
            for message in _refuse(503, "The MCP endpoint is starting or stopping; try again."):
                await send(message)
            return
        await self.manager.handle_request(scope, receive, send)


_endpoint = _Endpoint()


@asynccontextmanager
async def running():
    """Run the endpoint for the life of the web app (gcrm/api/main.py's lifespan)."""
    manager = StreamableHTTPSessionManager(
        app=server._mcp_server, json_response=True, stateless=True,
        security_settings=server.settings.transport_security,
    )
    async with manager.run():
        _endpoint.manager = manager
        try:
            yield
        finally:
            _endpoint.manager = None


def asgi_app():
    """The /mcp endpoint for the web app to mount, behind the token check."""
    return BearerAuth(_endpoint)


class BareMcpPath:
    """Serve `/mcp` as well as `/mcp/`. Without this the router answers `/mcp` with a 307
    to `/mcp/` that names http:// (it cannot see the proxy's https), and a connector
    client does not follow that: claude.ai showed "Couldn't connect" for the bare URL."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)
