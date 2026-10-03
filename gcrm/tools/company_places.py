"""Find the city a company is in, from its name alone (Google Places text search).

The LinkedIn export has no location, so this is the one source of a city for the
employers we create. Two rules keep it honest:

* Only the company name leaves the building — never anything about a person.
* A wrong city is worse than a blank one (the city drives scans, distance and
  duplicate detection), so a city is only accepted when exactly one place
  carries the company's name. Anything less goes to a human.

The request asks for the cheapest field set that contains an address: no
website, phone, rating or opening hours.
"""
import difflib
import logging
from dataclasses import dataclass, field

import httpx

from gcrm.linkedin import normalize_company
from gcrm.tools.search import GOOGLE_PLACES_URL

logger = logging.getLogger(__name__)

# Rough list price in USD per 1,000 Places text-search requests with address
# fields. An estimate from memory of Google's published pricing, which changes;
# a monthly free allowance may make the real cost zero. The Google Cloud billing
# console is the only authority on what a run actually cost.
ESTIMATED_USD_PER_1000 = 35
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.addressComponents"
MAX_RESULTS = 5  # enough to notice a chain, which is what makes a name ambiguous
CLOSE_NAME_RATIO = 0.9
# Statuses where retrying the next company would fail the same way (bad key,
# billing off, quota spent) — stop instead of burning through the list.
FATAL_STATUSES = frozenset({400, 401, 403, 429})
CITY_TYPES = ("locality", "postal_town", "administrative_area_level_3", "sublocality_level_1")


class PlacesError(Exception):
    """A lookup failed (network, quota, key). `fatal` means don't try the next one."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


@dataclass(frozen=True)
class CityDecision:
    outcome: str  # resolved | ambiguous | not_found
    city: str = ""
    country: str = ""
    place_id: str = ""
    candidates: list[dict] = field(default_factory=list)


def _component(place: dict, *types: str) -> dict | None:
    for wanted in types:
        for component in place.get("addressComponents", []):
            if wanted in component.get("types", []):
                return component
    return None


def _describe(place: dict) -> dict:
    city = _component(place, *CITY_TYPES)
    country = _component(place, "country")
    return {
        "name": (place.get("displayName") or {}).get("text", ""),
        "city": (city or {}).get("longText", ""),
        "country": ((country or {}).get("shortText") or "").upper(),
        "place_id": place.get("id", ""),
    }


def _name_matches(company_key: str, place_name: str) -> bool:
    normalized = normalize_company(place_name)
    if not normalized:
        return False
    return normalized == company_key or (
        difflib.SequenceMatcher(None, normalized, company_key).ratio() >= CLOSE_NAME_RATIO
    )


def decide_city(company_key: str, places: list[dict]) -> CityDecision:
    """Pure: choose a city from Places results, or say why not.

    resolved   exactly one distinct (city, country) among the places that carry
               the company's name
    ambiguous  the name appears in several cities (a chain) — a human decides
    not_found  nothing carries the name, or the named place has no city
    """
    described = [_describe(place) for place in places]
    offered = [{k: d[k] for k in ("name", "city", "country")} for d in described]
    named = [d for d in described if _name_matches(company_key, d["name"])]
    if not named:
        return CityDecision("not_found", candidates=offered)
    located = {(d["city"], d["country"]) for d in named if d["city"] and d["country"]}
    if not located:
        return CityDecision("not_found", candidates=offered)
    if len(located) > 1:
        return CityDecision("ambiguous", candidates=offered)
    city, country = next(iter(located))
    place = next(d for d in named if (d["city"], d["country"]) == (city, country))
    return CityDecision("resolved", city, country, place["place_id"], offered)


def lookup_places(company_name: str) -> list[dict]:
    """One billed Places text search for a company name. Returns the raw places
    ([] when Google knows none). Raises PlacesError on any failure."""
    from gcrm.config import GOOGLE_MAPS_API_KEY

    if not GOOGLE_MAPS_API_KEY:
        raise PlacesError("GOOGLE_MAPS_API_KEY is not set", fatal=True)
    try:
        response = httpx.post(
            GOOGLE_PLACES_URL,
            json={"textQuery": company_name, "languageCode": "de", "maxResultCount": MAX_RESULTS},
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("places", [])
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        raise PlacesError(f"Places API returned HTTP {status}", fatal=status in FATAL_STATUSES)
    except Exception as error:
        raise PlacesError(f"Places lookup failed: {type(error).__name__}")
