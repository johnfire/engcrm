"""Browser response policy, including nonces that survive an HTMX fragment swap."""
import re
import secrets

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gcrm.config import SESSION_COOKIE_SECURE

NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")


def request_nonce(headers: Headers) -> str:
    """A fragment uses its page's nonce; normal page navigations always mint one."""
    supplied = headers.get("x-csp-nonce", "")
    if headers.get("hx-request") == "true" and NONCE_PATTERN.fullmatch(supplied):
        return supplied
    return secrets.token_urlsafe(24)


def browser_headers(nonce: str, is_https: bool) -> dict[str, str]:
    policy = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; script-src-attr 'none'; "
        f"style-src 'self' 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; "
        "img-src 'self' data: https://*.tile.openstreetmap.org; font-src 'self'; "
        "connect-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; "
        "object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    headers = {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(self), microphone=(self), geolocation=(self), payment=(), usb=()",
    }
    if is_https:
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


class BrowserHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        nonce = request_nonce(Headers(scope=scope))
        scope.setdefault("state", {})["csp_nonce"] = nonce
        response_started = False

        async def secure_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                for name, value in browser_headers(nonce, SESSION_COOKIE_SECURE or scope.get("scheme") == "https").items():
                    headers.setdefault(name, value)
                if not scope.get("path", "").startswith("/static/"):
                    headers.setdefault("Cache-Control", "private, no-store")
            await send(message)

        try:
            await self.app(scope, receive, secure_send)
        except Exception:
            if not response_started:
                await JSONResponse({"detail": "Internal server error"}, status_code=500)(scope, receive, secure_send)
            raise
