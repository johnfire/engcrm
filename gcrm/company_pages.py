"""Recognise a company's LinkedIn and XING pages in web-search results.

Pure functions — no network. The URLs come from a search engine's result list, so
nothing here visits LinkedIn or XING. Only company pages are kept (people, jobs and
posts are not), and a page is only taken when every distinctive word of the
company's name is in its address, title or snippet: a wrong page is worse than none.
"""
import re
from urllib.parse import urlsplit

from gcrm.linkedin import GENERIC_TOKENS, LEGAL_FORMS, normalize_company

_LINKEDIN_COMPANY = re.compile(r"^/company/([^/?#]+)")
_XING_COMPANY = re.compile(r"^/(?:pages|companies)/([^/?#]+)")


def company_page_url(url: str) -> tuple[str, str] | None:
    """('linkedin' | 'xing', tidy page URL) for a company page, else None."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        match = _LINKEDIN_COMPANY.match(parts.path)
        return ("linkedin", f"https://www.linkedin.com/company/{match.group(1)}/") if match else None
    if host == "xing.com" or host.endswith(".xing.com"):
        match = _XING_COMPANY.match(parts.path)
        return ("xing", f"https://www.xing.com/pages/{match.group(1)}") if match else None
    return None


def distinctive_words(company_name: str) -> set[str]:
    """The words that say *which* company this is: not legal forms, not generic trade words."""
    words = set(normalize_company(company_name).split())
    return {word for word in words if len(word) >= 3 and word not in LEGAL_FORMS | GENERIC_TOKENS}


def names_company(search_result: dict, required_words: set[str]) -> bool:
    """True when every required word is in the result's address, title or snippet."""
    url_words = re.sub(r"[^a-z0-9]+", " ", (search_result.get("url") or "").lower())
    text = normalize_company(" ".join([
        url_words, search_result.get("title") or "", search_result.get("snippet") or "",
    ]))
    return bool(required_words) and required_words <= set(text.split())


def pick_company_pages(company_name: str, search_results: list[dict]) -> dict[str, str]:
    """{'linkedin_url': ..., 'xing_url': ...} for the first matching page per network."""
    required_words = distinctive_words(company_name)
    pages: dict[str, str] = {}
    for search_result in search_results:
        page = company_page_url(search_result.get("url") or "")
        if page is None or f"{page[0]}_url" in pages:
            continue
        if names_company(search_result, required_words):
            pages[f"{page[0]}_url"] = page[1]
    return pages
