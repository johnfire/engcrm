"""Module-level nodes for research."""

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from gcrm.vertical import SCAN_LEVELS

from ._utils import parse_json_response
from .prompts import extract_contacts_prompt
from .state import ResearchState

logger = logging.getLogger(__name__)


def init(state: ResearchState, dependencies) -> dict:
    level = state.get("level", 1)
    run_id = dependencies.start_run(
        "research_agent",
        {"city": state["city"], "country": state.get("country", "DE"), "level": level},
    )
    return {
        "run_id": run_id,
        "country": state.get("country", "DE"),
        "level": level,
        "maps_terms": SCAN_LEVELS.get(level, SCAN_LEVELS.get(1, {})).get("maps_terms", []),
        "raw_results": [],
        "contacts_to_save": [],
        "saved_ids": [],
        "errors": [],
        "summary": "",
    }


def run_maps_search(state: ResearchState, dependencies) -> dict:
    """Run each Google Maps term for this level. Collects structured venue data."""
    results = []
    for term in state.get("maps_terms", []):
        try:
            hits = dependencies.geo_search(term, state["city"], state.get("country", "DE"))
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
        state.get("level"),
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
    """Run up to 2 targeted web searches per level to supplement Maps data.
    Queries are read from SCAN_LEVELS[level]['web_queries'] in vertical.py.
    Falls back to building a query from maps_terms if none are defined."""
    level = state.get("level", 1)
    city = state["city"]
    level_info = SCAN_LEVELS.get(level, {})
    raw_queries = level_info.get("web_queries", [])
    if raw_queries:
        queries = [query.format(city=city) for query in raw_queries[:2]]
    else:
        maps_terms = level_info.get("maps_terms", [])
        label = level_info.get("label", "venues")
        fallback = " ".join(maps_terms[:3]) if maps_terms else label
        queries = [f"{fallback} {city}", f"{city} {label}"]
    web_results = list(state.get("raw_results", []))
    for query in queries:
        try:
            web_results.extend(dependencies.web_search(query))
        except Exception:
            pass
    return {"raw_results": web_results}


def fetch_pages(state: ResearchState, dependencies) -> dict:
    """Fetch top web result pages to get full contact details beyond snippets."""
    if not state.get("raw_results"):
        return {}
    seen = set()
    urls = []
    for result in state["raw_results"]:
        url = result.get("url", "") or result.get("website", "")
        if url and url not in seen and (not url.startswith("https://www.google")):
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


def extract_contacts(state: ResearchState, dependencies) -> dict:
    if not state.get("raw_results"):
        return {"contacts_to_save": []}
    level = state.get("level", 1)
    system, user = extract_contacts_prompt(
        dependencies.mission, state["city"], level, state["raw_results"]
    )
    try:
        response = dependencies.llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        contacts = parse_json_response(response.content)
        if not isinstance(contacts, list):
            raise ValueError("Expected a JSON array")
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [f"extract_contacts: {error}"],
            "contacts_to_save": [],
        }
    return {"contacts_to_save": contacts}


def fetch_missing_emails(state: ResearchState, dependencies) -> dict:
    """For each extracted contact with a website but no email, fetch the page
    and regex-extract an email, skipping noise/builder domains. Contacts with
    no website (or where no usable email turns up) are flagged _no_data=True so
    save_contacts records them as cannot_find_more_data."""
    contacts = state.get("contacts_to_save", [])
    if not contacts:
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
    for contact in contacts:
        if contact.get("email"):
            continue
        if not contact.get("website"):
            contact["_no_data"] = True
            no_data += 1
            continue
        try:
            text = dependencies.fetch_page(contact["website"])
            if not text:
                contact["_no_data"] = True
                no_data += 1
                continue
            for match in email_re.finditer(text):
                email = match.group(0).lower()
                domain = email.split("@")[1]
                if domain not in noise_domains:
                    contact["email"] = email
                    found += 1
                    logger.info("research: email found for %s — %s", contact.get("name", ""), email)
                    break
            else:
                contact["_no_data"] = True
                no_data += 1
        except Exception:
            contact["_no_data"] = True
            no_data += 1
    if found:
        logger.info("research: fetched emails for %d contact(s) in %s", found, state["city"])
    if no_data:
        logger.info(
            "research: %d contact(s) have no web presence in %s — will save as cannot_find_more_data",
            no_data,
            state["city"],
        )
    return {"contacts_to_save": contacts}


def save_contacts(state: ResearchState, dependencies) -> dict:
    level = state.get("level", 1)
    google_by_name = state.get("google_by_name", {})
    saved_ids = []
    for contact in state.get("contacts_to_save", []):
        try:
            status = "cannot_find_more_data" if contact.get("_no_data") else "candidate"
            google = google_by_name.get((contact.get("name") or "").strip().lower())
            contact_id = dependencies.save_contact(
                name=contact.get("name", ""),
                city=contact.get("city", state["city"]),
                country=contact.get("country", state.get("country", "DE")),
                type=contact.get("type", ""),
                website=contact.get("website", ""),
                email=contact.get("email", ""),
                phone=contact.get("phone", ""),
                notes=contact.get("notes", ""),
                scan_level=level,
                neighborhood=contact.get("neighborhood", ""),
                status=status,
                google=google,
            )
            if contact_id:
                saved_ids.append(contact_id)
        except Exception as error:
            logger.warning("save_contact failed for '%s': %s", contact.get("name", ""), error)
    return {"saved_ids": saved_ids}


def generate_report(state: ResearchState, dependencies) -> dict:
    n = len(state.get("saved_ids", []))
    errs = state.get("errors", [])
    city = state["city"]
    level = state.get("level", 1)
    if errs:
        summary = f"research_agent: {city} level {level} — {n} contacts saved, {len(errs)} error(s): {errs[0]}"
        status = "failed" if n == 0 else "completed"
    else:
        summary = f"research_agent: {city} level {level} — {n} new contacts saved"
        status = "completed"
    dependencies.finish_run(
        state.get("run_id", 0), status, summary, {"saved_count": n, "level": level, "errors": errs}
    )
    return {"summary": summary}
