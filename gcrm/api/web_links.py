"""Turn a stored website value into a URL a browser can safely be handed.

Website values reach the database from LLM enrichment, scraped directory
listings, business-card OCR and hand typing, so they arrive without a scheme
("acme.de"), padded with whitespace, or — worst case — as a "javascript:"
payload that would execute when someone clicks the rendered link. Every
template that renders a stored website as an anchor routes it through here.
"""
import re
from urllib.parse import urlparse

BROWSABLE_SCHEMES = ("http", "https")
_HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def browsable_url(stored_website: str | None) -> str | None:
    """Return an http(s) URL for `stored_website`, or None if it can't be one.

    A scheme-less value is assumed to be https. Anything carrying another
    scheme (javascript:, data:, mailto:) or lacking a host is rejected rather
    than linked, so a bad row degrades to plain text instead of a live link.
    """
    candidate = (stored_website or "").strip()
    if not candidate:
        return None
    if not _HAS_SCHEME.match(candidate):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in BROWSABLE_SCHEMES or "." not in parsed.netloc:
        return None
    return candidate
