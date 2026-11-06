"""Session-bound CSRF tokens for HTML forms, HTMX and same-origin fetch calls."""
import hmac
import re
import secrets
from urllib.parse import urlsplit

from fastapi import Request

from gcrm.config import APP_PUBLIC_URL, SESSION_COOKIE_SECURE

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FORM_OPEN = re.compile(r"<form\b[^>]*>", re.IGNORECASE)


def csrf_token(request: Request) -> str:
    if not isinstance(request.session.get("csrf_token"), str):
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


def origin_of(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def expected_origin(request: Request) -> str:
    if urlsplit(APP_PUBLIC_URL).netloc == request.url.netloc:
        return origin_of(APP_PUBLIC_URL)
    scheme = "https" if SESSION_COOKIE_SECURE else request.url.scheme
    return f"{scheme}://{request.url.netloc}"


async def accepts_browser_write(request: Request) -> bool:
    if request.method in SAFE_METHODS or request.url.path.startswith(("/api/", "/mcp/")) or request.url.path == "/mcp":
        return True
    origin = request.headers.get("origin")
    origin = origin if origin is not None else origin_of(request.headers.get("referer", ""))
    if origin != expected_origin(request) or request.headers.get("sec-fetch-site") == "cross-site":
        return False
    submitted = request.headers.get("x-csrf-token")
    if submitted is None:
        await request.body()  # Cache the body so the downstream form parser can read it too.
        submitted = (await request.form()).get("csrf_token")
    return isinstance(submitted, str) and hmac.compare_digest(submitted, csrf_token(request))


def protect_html_forms(html: str, token: str, nonce: str = "") -> str:
    field = f'<input type="hidden" name="csrf_token" value="{token}">'

    def protect_form(match: re.Match) -> str:
        opening = match.group()
        unsafe = re.search(r'\bmethod\s*=\s*[\"\x27]?(post|put|patch|delete)\b|\bhx-(post|put|patch|delete)\s*=', opening, re.IGNORECASE)
        return opening + field if unsafe else opening

    html = FORM_OPEN.sub(protect_form, html)
    script = (f'<meta name="csrf-token" content="{token}"><meta name="csp-nonce" content="{nonce}">'
              f'<script nonce="{nonce}" src="/static/csrf.js" defer></script>')
    return html.replace("</head>", script + "</head>", 1)
