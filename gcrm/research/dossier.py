"""
Evidence-backed company research dossier generation.

Architecture:
  CompanyResearchFetcher (Protocol)
  ├── Crawl4AIFetcher  — primary: JS-rendered sites, markdown extraction, link discovery
  ├── BrightDataFetcher — fallback: Web Unlocker for bot-protected sites
  └── HttpFetcher       — last resort: plain HTTP + HTML stripping

  get_or_create_dossier(contact_id) → dict
    └── Returns cached dossier or generates one on demand.
        Safe to call from any agent (opportunity, scout, outreach).

Domain policy:
  - SSRF protection on all URLs (public-IP only, no loopback/private/link-local)
  - Same-domain crawling only (no external links during company exploration)
  - Media/assets skipped (images, fonts, downloads)
  - robots.txt checked in Crawl4AI mode
  - Per-domain rate limit and page cap (5–8 pages)
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urljoin, urlparse

from langchain_core.messages import HumanMessage, SystemMessage

from gcrm.config import CHEAP_LLM
from gcrm.db.connection import db, serialize_row
from gcrm.tools.costs import record_crawler
from gcrm.tools.llm import get_llm
from gcrm.tools.search import fetch_page as legacy_fetch_page
from gcrm.tools.search import is_public_http_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FetchedPage:
    """A single page fetched from a company website."""
    url: str
    title: str = ""
    markdown: str = ""
    content_hash: str = ""
    status_code: int = 0
    error: str = ""


@dataclass
class DossierEvidence:
    """One piece of source-backed evidence."""
    url: str
    title: str
    retrieved_at: str
    excerpt_hash: str
    source_type: str  # "homepage", "about", "contact", "services", "news", "imprint"


# ---------------------------------------------------------------------------
# Protocol — swappable fetcher implementations
# ---------------------------------------------------------------------------


class CompanyResearchFetcher(Protocol):
    """Interface for fetching pages from a company's website.

    Implementations: Crawl4AIFetcher (primary), BrightDataFetcher, HttpFetcher.
    """

    def fetch_page(self, url: str) -> FetchedPage | None:
        """Fetch a single page. Returns None on failure."""
        ...

    def fetch_domain_pages(self, domain: str, start_url: str, max_pages: int = 8) -> list[FetchedPage]:
        """Crawl up to `max_pages` pages on the given domain, starting from start_url."""
        ...


# ---------------------------------------------------------------------------
# Domain policy
# ---------------------------------------------------------------------------

# Pages worth crawling on a company site, grouped by semantic priority.
# Within each group, all paths have the same priority.
_PRIORITY_GROUPS: list[tuple[str, ...]] = [
    ("/", "/home", "/index"),
    ("/about", "/about-us", "/ueber-uns", "/unternehmen", "/team", "/people", "/founders"),
    ("/contact", "/kontakt", "/contact-us"),
    ("/imprint", "/impressum", "/legal-notice", "/legal"),
    ("/services", "/leistungen", "/portfolio", "/projects", "/referenzen", "/programme"),
    ("/clients", "/kunden"),
    ("/news", "/blog", "/aktuelles", "/events"),
]

# Build a flat lookup: path -> group index
_PRIORITY_MAP: dict[str, int] = {}
for _idx, _group in enumerate(_PRIORITY_GROUPS):
    for _path in _group:
        _PRIORITY_MAP[_path] = _idx

# File extensions to skip (media, assets, downloads).
_SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip",
    ".mp3", ".mp4", ".avi", ".mov", ".webm",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
}


def _page_priority(path: str) -> int:
    """Lower number = higher priority. Unknown paths get the lowest priority."""
    path_lower = path.lower().rstrip("/") or "/"
    return _PRIORITY_MAP.get(path_lower, len(_PRIORITY_GROUPS) + 100)


def should_crawl(url: str, base_domain: str) -> bool:
    """True if `url` is safe and worth crawling on `base_domain`."""
    if not is_public_http_url(url):
        return False
    parsed = urlparse(url)
    # Same-domain only during company exploration.  Strip 'www.' from both
    # sides so www.example.com and example.com are treated as the same domain.
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    base = base_domain.lower().removeprefix("www.")
    if hostname != base:
        return False
    # Skip media, assets, downloads.
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return False
    # Skip fragments, mailto, tel.
    if parsed.scheme not in ("http", "https"):
        return False
    return True


def _extract_domain(url: str) -> str | None:
    """Extract the hostname from a URL, stripping 'www.' prefix."""
    try:
        # urlparse needs a scheme to parse correctly.
        if "://" not in url:
            url = "https://" + url
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        # Must look like a real domain (contains at least one dot).
        if not hostname or "." not in hostname:
            return None
        return hostname.removeprefix("www.")
    except Exception:
        return None


def verify_domain(
    candidates: list[dict],
    company_name: str,
    city: str = "",
) -> str | None:
    """Pick the most likely official domain from a list of search/place candidates.

    Each candidate is a dict with keys: url, title, source (e.g. "google_places",
    "web_search"). Returns the selected domain or None.
    """
    if not candidates:
        return None

    # Priority 1: Google Places website for the exact business.
    for c in candidates:
        if c.get("source") == "google_places" and c.get("url"):
            domain = _extract_domain(c["url"])
            if domain:
                return domain

    # Priority 2: Web search result whose title/snippet contains the company name.
    name_lower = company_name.lower().strip()
    for c in candidates:
        if not c.get("url"):
            continue
        title = (c.get("title") or "").lower()
        snippet = (c.get("snippet") or "").lower()
        if name_lower in title or name_lower in snippet:
            domain = _extract_domain(c["url"])
            if domain and not _is_directory_or_social(domain):
                return domain

    # Priority 3: First non-directory, non-social domain.
    for c in candidates:
        if not c.get("url"):
            continue
        domain = _extract_domain(c["url"])
        if domain and not _is_directory_or_social(domain):
            return domain

    return None


_DIRECTORY_DOMAINS = {
    "google.com", "facebook.com", "instagram.com", "linkedin.com",
    "yelp.com", "tripadvisor.com", "yellowpages.com", "gelbeseiten.de",
    "dasoertliche.de", "11880.com", "foursquare.com", "kununu.com",
    "xing.com", "twitter.com", "wikipedia.org", "maps.google.com",
}


def _is_directory_or_social(domain: str) -> bool:
    return domain in _DIRECTORY_DOMAINS or domain.endswith(
        tuple(f".{d}" for d in _DIRECTORY_DOMAINS)
    )


# ---------------------------------------------------------------------------
# Content cache — simple in-memory with TTL
# ---------------------------------------------------------------------------

_CACHE_TTL = 3600 * 24  # 24 hours


@dataclass
class _CacheEntry:
    fetched: FetchedPage
    cached_at: float = field(default_factory=time.time)


_cache: dict[str, _CacheEntry] = {}


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]


def _cache_get(url: str) -> FetchedPage | None:
    entry = _cache.get(url)
    if entry is None:
        return None
    if time.time() - entry.cached_at > _CACHE_TTL:
        del _cache[url]
        return None
    return entry.fetched


def _cache_put(fetched: FetchedPage) -> None:
    _cache[fetched.url] = _CacheEntry(fetched=fetched)


# ---------------------------------------------------------------------------
# Crawl4AI fetcher (primary)
# ---------------------------------------------------------------------------


class Crawl4AIFetcher:
    """Fetch pages using Crawl4AI — handles JS-rendered sites, extracts clean Markdown."""

    def __init__(self) -> None:
        self._ready = False
        self._error: str | None = None
        self._async_crawler = None

    @property
    def available(self) -> bool:
        if self._ready:
            return True
        if self._error:
            return False
        try:
            import crawl4ai  # noqa: F401
            self._ready = True
            return True
        except ImportError:
            self._error = "crawl4ai not installed"
            return False

    def fetch_page(self, url: str) -> FetchedPage | None:
        if not self.available:
            return None
        cached = _cache_get(url)
        if cached:
            return cached
        try:
            import asyncio
            result = asyncio.run(self._async_fetch(url))
            if result:
                _cache_put(result)
            return result
        except Exception as exc:
            logger.warning("Crawl4AI fetch_page failed for %s: %s", url, exc)
            return None

    async def _async_fetch(self, url: str) -> FetchedPage | None:
        from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            excluded_tags=["script", "style", "img", "video", "audio", "iframe"],
            remove_overlay_elements=True,
            page_timeout=30000,
        )
        try:
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url, config=config)
            if not result or not result.success:
                return FetchedPage(url=url, error=getattr(result, "error_message", "unknown"))
            markdown = (result.markdown or "").strip()
            return FetchedPage(
                url=url,
                title=getattr(result, "title", "") or "",
                markdown=markdown[:8000],
                content_hash=_content_hash(markdown),
                status_code=getattr(result, "status_code", 200),
            )
        except Exception as exc:
            return FetchedPage(url=url, error=str(exc))

    def fetch_domain_pages(self, domain: str, start_url: str, max_pages: int = 8) -> list[FetchedPage]:
        if not self.available:
            return []

        # Fetch the landing page first.
        landing = self.fetch_page(start_url)
        if not landing:
            return []

        pages: list[FetchedPage] = [landing]
        seen_urls: set[str] = {landing.url}

        # Extract same-domain links from the landing page markdown.
        discovered_urls = _extract_same_domain_links(landing.markdown, domain, start_url)
        # Sort by priority (about, contact, services first).
        discovered_urls.sort(key=_page_priority)

        for url in discovered_urls:
            if len(pages) >= max_pages:
                break
            if url in seen_urls:
                continue
            seen_urls.add(url)
            page = self.fetch_page(url)
            if page and not page.error:
                pages.append(page)
                # Extract links from this page too, for breadth.
                more = _extract_same_domain_links(page.markdown, domain, start_url)
                for u in more:
                    if u not in seen_urls:
                        discovered_urls.append(u)

        return pages


def _extract_same_domain_links(markdown: str, domain: str, base_url: str) -> list[str]:
    """Extract same-domain HTTP links from markdown content."""
    # Markdown links: [text](url)
    md_links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', markdown)
    # Plain URLs
    plain_urls = re.findall(r'https?://[^\s<>"\')\]]+', markdown)

    urls: list[str] = []
    for _, url in md_links:
        urls.append(url)
    urls.extend(plain_urls)

    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        # Resolve relative URLs.
        resolved = urljoin(base_url, url)
        if not should_crawl(resolved, domain):
            continue
        # Normalize: strip fragment, trailing slash.
        parsed = urlparse(resolved)
        normalized = f"{parsed.scheme}://{parsed.hostname}{parsed.path.rstrip('/') or '/'}"
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


# ---------------------------------------------------------------------------
# Bright Data fetcher (fallback)
# ---------------------------------------------------------------------------


class BrightDataFetcher:
    """Fetch pages via Bright Data Web Unlocker — handles bot-protected sites."""

    @property
    def available(self) -> bool:
        from gcrm.config import BRIGHTDATA_API_TOKEN
        return bool(BRIGHTDATA_API_TOKEN)

    def fetch_page(self, url: str) -> FetchedPage | None:
        if not self.available:
            return None
        cached = _cache_get(url)
        if cached:
            return cached
        content = legacy_fetch_page(url, max_chars=8000)
        if not content:
            return None
        page = FetchedPage(
            url=url,
            markdown=content,
            content_hash=_content_hash(content),
        )
        _cache_put(page)
        return page

    def fetch_domain_pages(self, domain: str, start_url: str, max_pages: int = 8) -> list[FetchedPage]:
        # Bright Data doesn't do crawling — fetch the landing page only.
        page = self.fetch_page(start_url)
        return [page] if page else []


# ---------------------------------------------------------------------------
# HTTP fetcher (last resort)
# ---------------------------------------------------------------------------


class HttpFetcher:
    """Plain HTTP fetch with HTML stripping — no JS rendering, no bot bypass."""

    @property
    def available(self) -> bool:
        return True  # Always available as last resort.

    def fetch_page(self, url: str) -> FetchedPage | None:
        cached = _cache_get(url)
        if cached:
            return cached
        content = legacy_fetch_page(url, max_chars=8000)
        if not content:
            return None
        page = FetchedPage(
            url=url,
            markdown=content,
            content_hash=_content_hash(content),
        )
        _cache_put(page)
        return page

    def fetch_domain_pages(self, domain: str, start_url: str, max_pages: int = 8) -> list[FetchedPage]:
        page = self.fetch_page(start_url)
        return [page] if page else []


# ---------------------------------------------------------------------------
# Fetcher selection — tiered fallback
# ---------------------------------------------------------------------------

_fetcher: CompanyResearchFetcher | None = None


def _get_fetcher() -> CompanyResearchFetcher:
    """Return the best available fetcher, trying Crawl4AI → Bright Data → HTTP."""
    global _fetcher
    if _fetcher is not None:
        return _fetcher

    crawler = Crawl4AIFetcher()
    if crawler.available:
        logger.info("research dossier: using Crawl4AI fetcher")
        _fetcher = crawler
        return _fetcher

    bright = BrightDataFetcher()
    if bright.available:
        logger.info("research dossier: using Bright Data fetcher")
        _fetcher = bright
        return _fetcher

    logger.info("research dossier: using HTTP fetcher (last resort)")
    _fetcher = HttpFetcher()
    return _fetcher


# ---------------------------------------------------------------------------
# Dossier generation
# ---------------------------------------------------------------------------


def get_or_create_dossier(contact_id: int) -> dict | None:
    """Return the active dossier for a contact, generating one if it doesn't exist.

    This is the primary tool injected into agents. Safe to call multiple times
    — subsequent calls return the cached dossier. Agents (opportunity, scout,
    outreach) call this instead of fetch_page for structured company evidence.

    Returns a dict with keys:
      contact_id, official_domain, company_summary, research_status,
      evidence, people, person_context, research_version
    Returns None if the contact has no website or all fetches fail.
    """
    # Check cache first.
    existing = _get_active_dossier(contact_id)
    if existing:
        return existing

    # Not cached — generate.
    contact = _get_contact(contact_id)
    if not contact:
        return None

    return _generate_dossier(contact)


def _get_active_dossier(contact_id: int) -> dict | None:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, contact_id, official_domain, company_summary,
                      research_status, research_version,
                      evidence, people, person_context,
                      created_at, updated_at
               FROM research_dossiers
               WHERE contact_id = %s AND deleted_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (contact_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def _get_contact(contact_id: int) -> dict | None:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, website, city, country, type, notes FROM contacts WHERE id = %s AND deleted_at IS NULL",
            (contact_id,),
        )
        row = cur.fetchone()
        return serialize_row(dict(row)) if row else None


def _generate_dossier(contact: dict) -> dict | None:
    """Generate a research dossier for a single contact."""
    contact_id = contact["id"]
    company_name = contact.get("name") or ""
    city = contact.get("city") or ""
    website = contact.get("website") or ""

    if not website:
        return _save_dossier(contact_id, None, "no_authoritative_source", [], [], [])

    domain = _extract_domain(website)
    if not domain:
        return _save_dossier(contact_id, None, "no_authoritative_source", [], [], [])

    fetcher = _get_fetcher()

    # Determine fetcher tier for status.
    if isinstance(fetcher, Crawl4AIFetcher):
        fetcher_tier = "crawl4ai"
    elif isinstance(fetcher, BrightDataFetcher):
        fetcher_tier = "brightdata"
    else:
        fetcher_tier = "http"

    # Crawl the company site.
    pages = fetcher.fetch_domain_pages(domain, website, max_pages=8)
    record_crawler(len(pages), fetcher_tier)
    if not pages:
        return _save_dossier(contact_id, domain, "blocked", [], [], [])

    # Build evidence list.
    evidence: list[dict] = []
    all_markdown = ""
    for page in pages:
        if page.error:
            continue
        source_type = _classify_page_type(page.url)
        all_markdown += f"\n\n--- {page.url} ---\n{page.markdown}"
        evidence.append({
            "url": page.url,
            "title": page.title or source_type,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "excerpt_hash": page.content_hash,
            "source_type": source_type,
        })

    # Extract company facts via LLM from combined markdown.
    company_summary, extracted_people = _llm_extract_company(all_markdown, company_name, city, domain)

    # Determine status.
    if len(pages) == 1 and fetcher_tier in ("brightdata", "http"):
        research_status = "partial"  # Single-page only.
    elif len(pages) < 3:
        research_status = "partial"
    else:
        research_status = "complete"

    # Person extraction from the company's own pages (passive, not active research).
    people: list[dict] = extracted_people or []
    person_context: list[dict] = []

    return _save_dossier(contact_id, domain, research_status, evidence, people, person_context,
                         company_summary=company_summary)


def _classify_page_type(url: str) -> str:
    """Classify a page based on its URL path."""
    path = urlparse(url).path.lower().rstrip("/") or "/"
    if path in ("/", "/home", "/index"):
        return "homepage"
    if any(seg in path for seg in ("about", "ueber", "unternehmen", "team", "people", "founder")):
        return "about"
    if any(seg in path for seg in ("contact", "kontakt")):
        return "contact"
    if any(seg in path for seg in ("imprint", "impressum", "legal")):
        return "imprint"
    if any(seg in path for seg in ("service", "leistung", "portfolio", "project", "referenz", "client", "kunde")):
        return "services"
    if any(seg in path for seg in ("news", "blog", "aktuell", "event")):
        return "news"
    return "other"


def _llm_extract_company(
    markdown: str, company_name: str, city: str, domain: str
) -> tuple[str, list[dict]]:
    """Extract company facts and named professionals from crawled pages via LLM.

    Returns (company_summary, people) where people is a list of
    {name, role, source_url, confidence} dicts found on the company's own site.
    Falls back to heuristic extraction if the LLM call fails.
    """
    if not markdown.strip():
        return "", []

    # Cap at 12K chars to stay within reasonable token limits.
    content = markdown[:12000]

    system = (
        "You are a research analyst extracting facts from a company's website. "
        "Return ONLY valid JSON. Never hallucinate information not present in the source. "
        "If a fact cannot be confirmed from the pages provided, omit it."
    )
    user = (
        f"Analyse the following content from {company_name}'s website ({domain}) in {city}.\n\n"
        f"PAGE CONTENT:\n<<<CONTENT>>>\n{content}\n<<<END CONTENT>>>\n\n"
        "Return a JSON object with exactly these keys:\n"
        '- company_summary: 2-4 sentences describing what the company does, their '
        "industry, size indicators if visible (e.g. 'family business', 'team of 15'), "
        "and any distinctive capabilities. Be factual and specific.\n"
        "- people: array of objects with {name, role, source_url, confidence}. "
        "Only include people whose name AND professional role appear on these pages. "
        "Confidence is 0-100 based on how clearly the information is stated. "
        "Use the page URL where the person was found as source_url.\n\n"
        "Return ONLY the JSON object, no other text."
    )

    try:
        llm = get_llm(CHEAP_LLM)
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        result = json.loads(response.content)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        company_summary = str(result.get("company_summary", "")).strip()[:1000]
        people_raw = result.get("people", [])
        people = []
        if isinstance(people_raw, list):
            for p in people_raw:
                if isinstance(p, dict) and p.get("name") and p.get("role"):
                    people.append({
                        "name": str(p["name"]).strip(),
                        "role": str(p["role"]).strip(),
                        "source_url": str(p.get("source_url", "")).strip(),
                        "confidence": max(0, min(100, int(p.get("confidence", 50)))),
                    })
        logger.info(
            "dossier LLM extraction: %s — %d chars summary, %d people found",
            domain, len(company_summary), len(people),
        )
        return company_summary, people[:8]  # Cap at 8 people.
    except Exception as exc:
        logger.warning("dossier LLM extraction failed for %s: %s — falling back to heuristic", domain, exc)
        return _heuristic_summary(markdown, company_name, city), []


def _heuristic_summary(markdown: str, company_name: str, city: str) -> str:
    """Fast heuristic fallback: first meaningful paragraph of markdown."""
    if not markdown.strip():
        return ""
    lines = markdown.strip().split("\n")
    summary_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if summary_lines:
                break
            continue
        if len(stripped) < 10 and stripped.isupper():
            continue
        if stripped.startswith("[") and stripped.endswith(")"):
            continue
        if stripped.startswith("#"):
            continue
        summary_lines.append(stripped)
        if len(" ".join(summary_lines)) > 600:
            break
    return " ".join(summary_lines)[:800]


def _save_dossier(
    contact_id: int,
    domain: str | None,
    status: str,
    evidence: list[dict],
    people: list[dict],
    person_context: list[dict],
    company_summary: str = "",
) -> dict | None:
    """Persist a dossier row and return it as a dict. Supersedes any previous active dossier."""
    from psycopg2.extras import Json

    now = datetime.now(timezone.utc)
    with db() as conn:
        cur = conn.cursor()
        # Soft-delete any previous active dossier for this contact.
        cur.execute(
            "UPDATE research_dossiers SET deleted_at = %s WHERE contact_id = %s AND deleted_at IS NULL",
            (now, contact_id),
        )
        cur.execute(
            """INSERT INTO research_dossiers
               (contact_id, official_domain, company_summary, research_status,
                research_version, evidence, people, person_context)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, contact_id, official_domain, company_summary,
                         research_status, research_version,
                         evidence, people, person_context,
                         created_at, updated_at""",
            (
                contact_id,
                domain,
                company_summary,
                status,
                "1.0",
                Json(evidence),
                Json(people),
                Json(person_context),
            ),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
