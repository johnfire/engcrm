"""Storefront-sign capture: vision extraction, business resolution, and
single-business research (enrichment + key-people lookup).

Parallels gcrm/tools/cards.py's photo->vision->confirm flow, but for a sign
(a bare business name, rarely a person) instead of a business card. Shares
card_captures (kind='sign'), the image volume, and the enrichment agent with
the card flow — see gcrm/api/routers/api_signs.py for the endpoints that wire
these together.
"""
import base64
import logging
import math
import re

from gcrm.prompts.signs import SIGN_SYSTEM_PROMPT
from gcrm.tools.cards import _content_to_text, _usage_cost

logger = logging.getLogger(__name__)

_EXTRACT_MODEL = "claude-haiku"                    # get_llm() key
_EXTRACT_MODEL_NAME = "claude-haiku-4-5-20251001"    # PRICING / response model name

# What the mobile client is told when extraction fails. Deliberately free of
# detail — the diagnosable version is in the server log.
_EXTRACTION_FAILED = "Could not read this sign. Enter the details manually or retake the photo."

# Directory/social domains that won't carry a business's own contact details —
# same list the enrichment agent skips (agents/gcrm-enrichment-agent/graph.py).
_SKIP_FETCH_DOMAINS = re.compile(
    r"(google\.|facebook\.|instagram\.|yelp\.|tripadvisor\.|gelbeseiten\.|"
    r"yellowpages\.|booking\.|maps\.|wikipedia\.|openstreetmap\.)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Vision extraction
# ---------------------------------------------------------------------------
def extract_sign_fields(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Run Claude Haiku 4.5 vision on a storefront-sign image.

    Returns {"fields": {...}, "model": str, "cost_usd": float}. `fields` always
    has an `is_sign` key; on any failure it's {"is_sign": False, "error": ...},
    where `error` is a fixed client-safe string — the real cause goes to the log.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from gcrm.json_parsing import parse_llm_json
    from gcrm.tools.llm import get_llm

    b64 = base64.b64encode(image_bytes).decode("ascii")
    user = HumanMessage(content=[
        {"type": "text", "text": "Extract this business storefront sign."},
        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
    ])
    try:
        resp = get_llm(_EXTRACT_MODEL).invoke([SystemMessage(content=SIGN_SYSTEM_PROMPT), user])
        fields = parse_llm_json(_content_to_text(resp.content))
        usage = getattr(resp, "usage_metadata", None) or {}
        cost = _usage_cost(_EXTRACT_MODEL_NAME, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    except Exception:
        # The detail stays in the server log; the mobile client gets a fixed
        # string. str(error) here reached the app verbatim, and an upstream SDK
        # error can carry request URLs, model wiring, even key fragments.
        logger.exception("sign extraction failed")
        return {"fields": {"is_sign": False, "error": _EXTRACTION_FAILED}, "model": _EXTRACT_MODEL_NAME, "cost_usd": 0.0}

    fields.setdefault("is_sign", True)
    return {"fields": fields, "model": _EXTRACT_MODEL_NAME, "cost_usd": cost}


# ---------------------------------------------------------------------------
# Business resolution (Google Places, name + optional GPS -> canonical Place)
# ---------------------------------------------------------------------------
def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters — used to pick the nearest Places match
    to the sign's capture GPS when several results share a name."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_business(name: str, gps: tuple[float, float] | None = None, country: str = "DE") -> dict | None:
    """
    Resolve a bare business name (+ optional GPS) to a canonical Google Place.

    Returns {name, place_id, address, city, website, phone, google_data} or None
    when unresolved — no API key set, no results, or the search failed. Callers
    must fall back to the raw sign name in that case (degrade, never crash).
    """
    name = (name or "").strip()
    if not name:
        return None
    from gcrm.tools.search import google_maps_search

    results = google_maps_search(name, city="", country=country, pages=1)
    if not results:
        return None
    if gps:
        lat, lng = gps

        def distance(result: dict) -> float:
            rlat, rlng = result.get("latitude"), result.get("longitude")
            if rlat is None or rlng is None:
                return float("inf")
            return _haversine_m(lat, lng, rlat, rlng)

        results = sorted(results, key=distance)
    best = results[0]
    return {
        "name": best.get("name", name),
        "place_id": best.get("place_id", ""),
        "address": best.get("address", ""),
        "city": best.get("city", ""),
        "website": best.get("website", ""),
        "phone": best.get("phone", ""),
        "google_data": best.get("google_data"),
    }


def build_contact_fields(business_name: str, extracted: dict, place: dict | None) -> dict:
    """
    Shape confirmed sign data into the fields dict cards.promote_to_contact()
    expects (company/city/website/phone/note/address/industry). `place` is the
    resolved Google Place iff the user accepted it on the confirm screen —
    otherwise fall back to whatever the vision extraction found on the sign.
    """
    industry = (extracted.get("business_type") or "").strip()
    note = (extracted.get("tagline") or extracted.get("note") or "").strip()
    if place:
        return {
            "company": business_name or place.get("name", ""),
            "city": place.get("city", "") or "",
            "industry": industry,
            "website": place.get("website") or extracted.get("website") or "",
            "phone": place.get("phone") or extracted.get("phone") or "",
            "address": place.get("address", ""),
            "note": note,
        }
    return {
        "company": business_name,
        "industry": industry,
        "website": (extracted.get("website") or "").strip(),
        "phone": (extracted.get("phone") or "").strip(),
        "note": note,
    }


# ---------------------------------------------------------------------------
# Key-people lookup
# ---------------------------------------------------------------------------
def find_key_people(contact: dict, max_people: int = 5) -> list[dict]:
    """
    Search the web for key people at a business (owner, manager, decision-
    makers) and ask the cheap LLM to extract them. Best-effort: any failure
    (search, fetch, or the LLM call) returns [] rather than raising.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from gcrm.config import CHEAP_LLM
    from gcrm.json_parsing import parse_llm_json
    from gcrm.prompts.enrichment import find_people_prompt
    from gcrm.tools import fetch_page, web_search
    from gcrm.tools.llm import get_llm

    name = (contact.get("name") or "").strip()
    if not name:
        return []
    city = contact.get("city") or ""
    country = contact.get("country") or "DE"
    query = (
        f"{name} {city} Team Ansprechpartner Impressum"
        if country in ("DE", "AT", "CH")
        else f"{name} {city} team contact person"
    )
    try:
        results = web_search(query)
    except Exception:
        logger.warning("find_key_people: search failed for %s", name)
        return []
    if not results:
        return []

    pages = []
    for result in results[:2]:
        url = result.get("url", "")
        if not url or _SKIP_FETCH_DOMAINS.search(url):
            continue
        try:
            text = fetch_page(url)
            if text:
                pages.append(f"[Page: {url}]\n{text[:2000]}")
        except Exception:
            pass

    system, user = find_people_prompt(contact, results, pages)
    try:
        response = get_llm(CHEAP_LLM).invoke([SystemMessage(content=system), HumanMessage(content=user)])
        data = parse_llm_json(_content_to_text(response.content))
    except Exception:
        logger.warning("find_key_people: LLM extraction failed for %s", name)
        return []

    people = data if isinstance(data, list) else data.get("people", []) if isinstance(data, dict) else []
    return people[:max_people] if isinstance(people, list) else []


def promote_people(contact_id: int, people: list[dict]) -> list[int]:
    """
    Create a people-table entry for each key person research found, linked to
    the business contact. Best-effort per person — one bad entry must not drop
    the rest.
    """
    from gcrm.tools.db import save_person

    ids: list[int] = []
    for person in people:
        name = (person.get("name") or "").strip()
        if not name:
            continue
        try:
            ids.append(save_person(
                name=name,
                title=(person.get("role") or person.get("title") or "").strip(),
                email=(person.get("email") or "").strip(),
                phone=(person.get("phone") or "").strip(),
                contact_id=contact_id,
                source="sign_research",
            ))
        except Exception:
            logger.exception("promote_people: failed to save %r for contact %s", name, contact_id)
    return ids


# ---------------------------------------------------------------------------
# Background research (confirm -> enrich + find people -> notify)
# ---------------------------------------------------------------------------
def research_business(contact_id: int) -> None:
    """
    Background job kicked off on sign confirm: fill business details via the
    shared enrichment agent, look up key people, then notify. Each stage is
    best-effort and isolated — one stage failing must not block the others or
    the final notification.
    """
    from gcrm.tools.cards import _run_enrichment_agent
    from gcrm.tools.db import get_contact

    try:
        _run_enrichment_agent(contact_id)
    except Exception:
        logger.exception("research_business: enrichment failed for contact %s", contact_id)

    people_found = 0
    try:
        contact = get_contact(contact_id)
        people = find_key_people(contact) if contact else []
        people_found = len(promote_people(contact_id, people))
    except Exception:
        logger.exception("research_business: people lookup failed for contact %s", contact_id)

    try:
        from gcrm.api.push import send_push_to_all
        c = get_contact(contact_id) or {}
        body = f"{c.get('name', 'Business')} researched"
        if people_found:
            body += f" — {people_found} key {'person' if people_found == 1 else 'people'} found"
        send_push_to_all(title="Business researched", body=body, data={"screen": "contacts"})
    except Exception:
        logger.debug("research_business: push failed", exc_info=True)
