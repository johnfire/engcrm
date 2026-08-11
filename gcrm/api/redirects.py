"""Same-origin redirect construction for the web UI.

Every 303 the HTML routes issue has to land back inside this app. Building the
Location header by hand made that a promise each call site had to keep on its
own — and the contacts delete/unflag routes broke it by echoing the browser's
`Referer` straight back. That header is attacker-controlled: a phishing page can
POST a form at us and bounce the logged-in admin to a look-alike login screen
wearing our redirect. Routing every redirect through local_path() turns the
promise into one enforced rule, so a scheme or a host can never survive into the
Location header no matter what a future call site passes in.
"""
from urllib.parse import urlencode, urlsplit

from fastapi.responses import RedirectResponse

DEFAULT_FALLBACK = "/"


def local_path(candidate: str, fallback: str = DEFAULT_FALLBACK) -> str:
    """Reduce `candidate` to an in-app path (+query), or return `fallback`.

    Rejects anything that could point off-origin:
      - absolute URLs ("https://evil.test/x") — urlsplit reports a scheme
      - protocol-relative URLs ("//evil.test") — urlsplit reports a netloc
      - the backslash variant ("/\\evil.test"), which browsers normalize to
        "//evil.test" but urlsplit leaves sitting in the path
      - relative paths ("contacts/"), which resolve against whatever the
        current page happens to be
    """
    if not candidate:
        return fallback
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return fallback
    path = parts.path
    if not path.startswith("/") or path[1:2] in ("/", "\\"):
        return fallback
    return f"{path}?{parts.query}" if parts.query else path


def local_redirect(
    path: str,
    fallback: str = DEFAULT_FALLBACK,
    status_code: int = 303,
    **params: str,
) -> RedirectResponse:
    """303 to the in-app `path`, with `params` URL-encoded onto the query string.

    Values are encoded with urlencode(), so a param can never smuggle its own
    `&`/`#` or escape the query string into the path.
    """
    target = local_path(path, fallback)
    if params:
        separator = "&" if "?" in target else "?"
        target = f"{target}{separator}{urlencode(params)}"
    return RedirectResponse(url=target, status_code=status_code)
