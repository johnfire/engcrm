"""Module-level nodes for research."""

import logging
import re
from urllib.parse import urljoin, urlparse

from langchain_core.messages import HumanMessage, SystemMessage

from gcrm.vertical import SCAN_LEVELS

from ._utils import parse_json_response
from .prompts import extract_organizations_prompt
from .state import ResearchState

logger = logging.getLogger(__name__)


def init(state: ResearchState, dependencies) -> dict:
    levels = state.get("levels") or [1]
    run_id = dependencies.start_run(
        "research_agent",
        {"city": state["city"], "country": state.get("country", "DE"), "levels": levels},
    )
    maps_terms = []
    for level in levels:
        maps_terms.extend(SCAN_LEVELS.get(level, {}).get("maps_terms", []))
    return {
        "run_id": run_id,
        "country": state.get("country", "DE"),
        "levels": levels,
        "maps_terms": maps_terms or SCAN_LEVELS[1]["maps_terms"],
        "raw_results": [],
        "organizations_to_save": [],
        "saved_ids": [],
        "errors": [],
        "summary": "",
    }


def run_maps_search(state: ResearchState, dependencies) -> dict:
    """Run each Google Maps term for the requested level(s). Collects structured
    venue data, geo-restricted to a circle instead of the city when this is an
    area/GPS-radius scan."""
    results = []
    for term in state.get("maps_terms", []):
        try:
            hits = dependencies.geo_search(
                term,
                state["city"],
                state.get("country", "DE"),
                lat=state.get("latitude"),
                lon=state.get("longitude"),
                radius_m=state.get("radius_m"),
            )
            results.extend(hits)
        except Exception as error:
            logger.warning("maps_search term '%s' failed (non-fatal): %s", term, error)
    seen = set()
    deduped = []
    for result in results:
        key = result.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(result)
    return {"raw_results": deduped}


def select_new_chunk(state: ResearchState, dependencies) -> dict:
    """Keep only businesses not already saved for this city, alphabetically, up
    to `cutoff` — so repeated scans march through the full list instead of
    redoing the top results. The already-saved contacts are the implicit cursor."""
    businesses = [b for b in state.get("raw_results", []) if b.get("name")]
    if dependencies.get_existing_names is None:
        return {
            "raw_results": businesses,
            "new_found": len(businesses),
            "scan_complete": True,
            "google_by_name": {},
        }
    existing = dependencies.get_existing_names(state["city"], state.get("country", "DE"))
    new_ones = [b for b in businesses if b["name"].strip().lower() not in existing]
    new_ones.sort(key=lambda business: business["name"].strip().lower())
    chunk = new_ones[: dependencies.cutoff]
    google_by_name = {b["name"].strip().lower(): b for b in chunk}
    complete = len(new_ones) <= dependencies.cutoff
    logger.info(
        "research: %s L%s — %d new of %d found; scanning %d this pass (complete=%s)",
        state["city"],
        state.get("levels"),
        len(new_ones),
        len(businesses),
        len(chunk),
        complete,
    )
    return {
        "raw_results": chunk,
        "new_found": len(new_ones),
        "scan_complete": complete,
        "google_by_name": google_by_name,
    }


def run_web_search(state: ResearchState, dependencies) -> dict:
    """Run up to 2 targeted web searches per requested level to supplement Maps
    data. Queries are read from SCAN_LEVELS[level]['web_queries'] in vertical.py.
    Falls back to building a query from maps_terms if none are defined."""
    city = state["city"]
    queries = []
    for level in state.get("levels") or [1]:
        level_info = SCAN_LEVELS.get(level, {})
        raw_queries = level_info.get("web_queries", [])
        if raw_queries:
            queries.extend(query.format(city=city) for query in raw_queries[:2])
        else:
            maps_terms = level_info.get("maps_terms", [])
            label = level_info.get("label", "venues")
            fallback = " ".join(maps_terms[:3]) if maps_terms else label
            queries.extend([f"{fallback} {city}", f"{city} {label}"])
    web_results = list(state.get("raw_results", []))
    for query in queries:
        try:
            web_results.extend(dependencies.web_search(query))
        except Exception:
            pass
    return {"raw_results": web_results}


def _is_google_host(url: str) -> bool:
    """Google's own result pages carry no contact detail worth fetching.

    Matched on the parsed hostname rather than a URL prefix: a search result for
    "https://www.google.evil.test/" carries the prefix but is somebody else's
    server, and prefix-matching would have skipped a real page (or, read the
    other way, let a look-alike host pose as one we trust).
    """
    host = (urlparse(url).hostname or "").lower()
    return host == "google.com" or host.endswith(".google.com")


def fetch_pages(state: ResearchState, dependencies) -> dict:
    """Fetch top web result pages to get full contact details beyond snippets."""
    if not state.get("raw_results"):
        return {}
    seen = set()
    urls = []
    for result in state["raw_results"]:
        url = result.get("url", "") or result.get("website", "")
        if url and url not in seen and not _is_google_host(url):
            seen.add(url)
            urls.append(url)
    pages = []
    for url in urls[:3]:
        content = dependencies.fetch_page(url)
        if content:
            pages.append({"source": "page", "url": url, "content": content[:1500]})
    if pages:
        return {"raw_results": state["raw_results"] + pages}
    return {}


def extract_organizations(state: ResearchState, dependencies) -> dict:
    if not state.get("raw_results"):
        return {"organizations_to_save": []}
    levels = state.get("levels") or [1]
    system, user = extract_organizations_prompt(
        dependencies.mission, state["city"], levels, state["raw_results"]
    )
    try:
        response = dependencies.llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        organizations = parse_json_response(response.content)
        if not isinstance(organizations, list):
            raise ValueError("Expected a JSON array")
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [f"extract_organizations: {error}"],
            "organizations_to_save": [],
        }
    return {"organizations_to_save": organizations}


# Tried in order, after the homepage, before giving up on an org with a
# website. Kontakt/Impressum carry a legal disclosure requirement in Germany
# (TMG) and almost always list a real email, but it's rarely on the homepage.
CONTACT_SUBPATHS = ("/kontakt", "/contact", "/impressum", "/about")


def _find_email(text: str, email_re: re.Pattern, noise_domains: set) -> str | None:
    for match in email_re.finditer(text):
        email = match.group(0).lower()
        if email.split("@")[1] not in noise_domains:
            return email
    return None


def fetch_missing_emails(state: ResearchState, dependencies) -> dict:
    """For each extracted contact with a website but no email, fetch the
    homepage and, if that turns up nothing, a short list of likely contact
    subpaths (kontakt/contact/impressum/about), regex-extracting an email and
    skipping noise/builder domains. Contacts with no website (or where no
    usable email turns up anywhere) are flagged _no_data=True so save_contacts
    records them with the research_exhausted flag raised."""
    organizations = state.get("organizations_to_save", [])
    if not organizations:
        return {}
    email_re = re.compile("[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}")
    noise_domains = {
        "example.com",
        "sentry.io",
        "wixpress.com",
        "squarespace.com",
        "wordpress.com",
        "shopify.com",
        "amazonaws.com",
        "googletagmanager.com",
    }
    found = 0
    no_data = 0
    for organization in organizations:
        if organization.get("email"):
            continue
        website = organization.get("website")
        if not website:
            organization["_no_data"] = True
            no_data += 1
            continue
        email = None
        try:
            for url in (website, *(urljoin(website, path) for path in CONTACT_SUBPATHS)):
                text = dependencies.fetch_page(url)
                if not text:
                    continue
                email = _find_email(text, email_re, noise_domains)
                if email:
                    break
        except Exception:
            email = None
        if email:
            organization["email"] = email
            found += 1
            logger.info("research: email found for %s — %s", organization.get("name", ""), email)
        else:
            organization["_no_data"] = True
            no_data += 1
    if found:
        logger.info("research: fetched emails for %d contact(s) in %s", found, state["city"])
    if no_data:
        logger.info(
            "research: %d contact(s) have no web presence in %s — saving with research_exhausted",
            no_data,
            state["city"],
        )
    return {"organizations_to_save": organizations}


def save_organizations(state: ResearchState, dependencies) -> dict:
    # scan_level records which level's terms this run searched under. For a
    # multi-level run the levels were searched together and results deduped
    # across them, so a single found business can't be attributed to one
    # level over another — it's tagged with the first requested level as a
    # representative value rather than left blank.
    level = (state.get("levels") or [1])[0]
    google_by_name = state.get("google_by_name", {})
    saved_ids = []
    for organization in state.get("organizations_to_save", []):
        try:
            research_exhausted = bool(organization.get("_no_data"))
            google = google_by_name.get((organization.get("name") or "").strip().lower())
            contact_id = dependencies.save_organization(
                name=organization.get("name", ""),
                city=organization.get("city", state["city"]),
                country=organization.get("country", state.get("country", "DE")),
                type=organization.get("type", ""),
                website=organization.get("website", ""),
                email=organization.get("email", ""),
                phone=organization.get("phone", ""),
                notes=organization.get("notes", ""),
                scan_level=level,
                neighborhood=organization.get("neighborhood", ""),
                research_exhausted=research_exhausted,
                google=google,
            )
            if contact_id:
                saved_ids.append(contact_id)
        except Exception as error:
            logger.warning("save_organization failed for '%s': %s", organization.get("name", ""), error)
    return {"saved_ids": saved_ids}


def generate_report(state: ResearchState, dependencies) -> dict:
    n = len(state.get("saved_ids", []))
    errs = state.get("errors", [])
    city = state["city"]
    levels = state.get("levels") or [1]
    level_label = ",".join(str(level) for level in levels)
    if errs:
        summary = f"research_agent: {city} level {level_label} — {n} contacts saved, {len(errs)} error(s): {errs[0]}"
        status = "failed" if n == 0 else "completed"
    else:
        summary = f"research_agent: {city} level {level_label} — {n} new contacts saved"
        status = "completed"
    dependencies.finish_run(
        state.get("run_id", 0), status, summary, {"saved_count": n, "levels": levels, "errors": errs}
    )
    return {"summary": summary}
