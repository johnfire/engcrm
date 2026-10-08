"""Suggest indexed LinkedIn profiles for a scanned person; never select one."""
import logging
import re
import unicodedata
from urllib.parse import urlsplit

from ddgs import DDGS

from gcrm.linkedin import normalize_linkedin_url

logger = logging.getLogger(__name__)


def normalize_profile_url(value: str | None) -> str | None:
    """Accept individual profiles only, excluding company and search pages."""
    canonical = normalize_linkedin_url(value)
    if not canonical or not re.fullmatch(r"/in/[^/\s]+", urlsplit(canonical).path):
        return None
    try:
        original = urlsplit(value if "://" in (value or "") else f"https://{value}")
        invalid_authority = original.username or original.password or original.port not in (None, 80, 443)
    except ValueError:
        return None
    if invalid_authority:
        return None
    return canonical


def search_text(value: str) -> str:
    """Normalize accents and punctuation for names and literal search terms."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(letter for letter in decomposed if not unicodedata.combining(letter))
    return " ".join(re.findall(r"[^\W_]+", without_accents))


def profile_candidates(matches: list[dict], name: str) -> list[dict]:
    required_names = set(search_text(name).split())
    candidates = {}
    for match in matches:
        url = normalize_profile_url(match.get("href"))
        title = str(match.get("title") or "")[:300]
        snippet = str(match.get("body") or "")[:600]
        if not url or not required_names.issubset(set(search_text(title + " " + snippet).split())):
            continue
        candidates.setdefault(url, {"url": url, "title": title, "snippet": snippet})
    return list(candidates.values())[:3]


def find_capture_profiles(name: str, company: str = "", city: str = "") -> dict:
    literal_name = search_text(name)
    if len(literal_name.split()) < 2:
        return {"status": "needs_name", "candidates": []}
    context = " ".join(filter(None, [search_text(company), search_text(city)]))
    query = f'site:linkedin.com/in/ "{literal_name}" {context}'.strip()
    try:
        matches = DDGS(timeout=8).text(query, max_results=8)
        candidates = profile_candidates(matches, name)
    except Exception:
        logger.exception("LinkedIn capture search unavailable")
        return {"status": "unavailable", "candidates": []}
    return {"status": "found" if candidates else "no_match", "candidates": candidates}
