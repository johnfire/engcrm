"""
Web and geographic search tools.
geo_search uses the Overpass API (OpenStreetMap) — no API key required.
google_maps_search uses Google Places API (New) — requires GOOGLE_MAPS_API_KEY.
web_search uses DuckDuckGo — no API key required.
"""
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import httpx
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = (10, 60)  # (connect, read)

GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

# Maps industry names to OpenStreetMap tag queries.
# Each entry is a list of (key, value) pairs tried in a single union query.
INDUSTRY_OSM_TAGS: dict[str, list[tuple[str, str]]] = {
    "gallery":     [("amenity", "gallery"), ("tourism", "gallery"), ("shop", "art")],
    "restaurant":  [("amenity", "restaurant")],
    "hotel":       [("tourism", "hotel")],
    "cafe":        [("amenity", "cafe")],
    "museum":      [("tourism", "museum")],
    "office":      [("office", "company"), ("office", "yes")],
    "coworking":   [("amenity", "coworking_space")],
    "bar":         [("amenity", "bar")],
}


def _build_overpass_query(city: str, tags: list[tuple[str, str]], country: str = "DE") -> str:
    area_filter = f'area["name"="{city}"]["ISO3166-2"~"^{country}"]->.a;'
    node_clauses = "\n".join(
        f'  node["{k}"="{v}"](area.a);' for k, v in tags
    )
    return f"""
[out:json][timeout:30];
{area_filter}
(
{node_clauses}
);
out center tags;
""".strip()


def geo_search(query: str, city: str, country: str = "DE") -> list[dict]:
    """
    Search for venues in a city using OpenStreetMap's Overpass API.
    `query` is used to determine the OSM tag set (matched by keyword).
    Returns list of dicts with: name, address, city, country, website, phone.
    """
    # Match query to tag set — fall back to generic text search tags
    industry_key = next(
        (industry for industry in INDUSTRY_OSM_TAGS if industry in query.lower()),
        None,
    )
    tags = INDUSTRY_OSM_TAGS.get(industry_key, [("name", "*")])

    overpass_q = _build_overpass_query(city, tags, country)
    try:
        resp = httpx.post(
            OVERPASS_URL,
            data={"data": overpass_q},
            timeout=OVERPASS_TIMEOUT,
            verify=True,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as error:
        logger.warning("geo_search failed for %s/%s: %s", city, query, error)
        return []

    results = []
    for el in elements:
        tags_data = el.get("tags", {})
        name = tags_data.get("name", "")
        if not name:
            continue
        results.append({
            "name": name,
            "address": " ".join(filter(None, [
                tags_data.get("addr:street", ""),
                tags_data.get("addr:housenumber", ""),
            ])),
            "city": city,
            "country": country,
            "website": tags_data.get("website", tags_data.get("contact:website", "")),
            "phone": tags_data.get("phone", tags_data.get("contact:phone", "")),
            "email": tags_data.get("email", tags_data.get("contact:email", "")),
        })

    logger.info("geo_search: %d results for '%s' in %s", len(results), query, city)
    return results


def google_maps_search(query: str, city: str, country: str = "DE", pages: int = 3) -> list[dict]:
    """
    Search for venues using Google Places API (New).
    Paginates up to 3 pages (max 60 results) via nextPageToken, and extracts the
    neighborhood (sublocality) from each result's address components.
    Returns dicts: name, place_id, address, city, country, website, phone, email,
    neighborhood. place_id is a Basic-tier field (no extra cost on top of the
    Enterprise fields already requested here).
    Falls back to empty list if the API key is missing or a request fails.
    """
    from gcrm.config import GOOGLE_MAPS_API_KEY
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("google_maps_search: GOOGLE_MAPS_API_KEY not set")
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        # Enterprise tier (the tier we already pay for via website + phone). Adds
        # status/rating/types/hours at no extra tier. No Atmosphere fields
        # (editorialSummary/reviews/photos) which would bump the SKU.
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.addressComponents,"
            "places.websiteUri,places.nationalPhoneNumber,places.internationalPhoneNumber,"
            "places.location,places.businessStatus,places.types,places.primaryType,"
            "places.primaryTypeDisplayName,places.rating,places.userRatingCount,"
            "places.regularOpeningHours,places.googleMapsUri,nextPageToken"
        ),
    }

    results: list[dict] = []
    page_token = None
    for page in range(pages):  # up to pages × 20 results
        payload = {
            "textQuery": f"{query} {city}",
            "languageCode": "de",
            "regionCode": country,
            "maxResultCount": 20,
        }
        if page_token:
            payload["pageToken"] = page_token
        try:
            resp = httpx.post(GOOGLE_PLACES_URL, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            places = data.get("places", [])
            page_token = data.get("nextPageToken")
        except Exception as error:
            logger.warning("google_maps_search failed for '%s' in %s (page %d): %s", query, city, page + 1, error)
            break

        for place in places:
            name = place.get("displayName", {}).get("text", "")
            if not name:
                continue
            neighborhood = ""
            for component in place.get("addressComponents", []):
                types = component.get("types", [])
                if "sublocality_level_1" in types or "neighborhood" in types:
                    neighborhood = component.get("longText", "")
                    break
            location = place.get("location", {})
            results.append({
                "name": name,
                "place_id": place.get("id", ""),
                "address": place.get("formattedAddress", ""),
                "city": city,
                "country": country,
                "website": place.get("websiteUri", ""),
                "phone": place.get("nationalPhoneNumber", "") or place.get("internationalPhoneNumber", ""),
                "email": "",
                "neighborhood": neighborhood,
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "business_status": place.get("businessStatus", ""),
                "rating": place.get("rating"),
                "user_ratings": place.get("userRatingCount"),
                "google_data": place,   # full payload — nothing lost
            })

        if not page_token:
            break

    logger.info("google_maps_search: %d results for '%s' in %s", len(results), query, city)
    return results


BRIGHTDATA_UNLOCKER_URL = "https://api.brightdata.com/request"
BRIGHTDATA_UNLOCKER_ZONE = "mcp_unlocker"


def is_public_http_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves entirely to public IPs.
    Blocks SSRF to loopback/private/link-local/reserved ranges, including the
    cloud metadata endpoint at 169.254.169.254."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def fetch_page(url: str, max_chars: int = 3000) -> str:
    """
    Fetch a web page and return its content as markdown.
    Uses Bright Data Web Unlocker (bot-bypass) when BRIGHTDATA_API_TOKEN is set,
    falls back to plain httpx + HTML stripping.
    """
    if not is_public_http_url(url):
        logger.warning("fetch_page: refusing non-public or unsafe URL: %s", url)
        return ""
    from gcrm.config import BRIGHTDATA_API_TOKEN
    if BRIGHTDATA_API_TOKEN:
        try:
            resp = httpx.post(
                BRIGHTDATA_UNLOCKER_URL,
                headers={
                    "Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "zone": BRIGHTDATA_UNLOCKER_ZONE,
                    "url": url,
                    "format": "raw",
                    "data_format": "markdown",
                },
                timeout=30,
            )
            resp.raise_for_status()
            logger.debug("fetch_page (brightdata): %s — %d chars", url, len(resp.text))
            return resp.text[:max_chars]
        except Exception as error:
            logger.debug("brightdata fetch_page failed for %s: %s — falling back", url, error)

    # Fallback: plain httpx with HTML stripping. Redirects must be followed
    # explicitly so every destination gets the same SSRF validation as the URL
    # supplied by the caller.
    import re
    try:
        current_url = url
        for _ in range(5):
            resp = httpx.get(current_url, timeout=10, follow_redirects=False, headers={
                "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"
            })
            if not resp.is_redirect:
                break
            location = resp.headers.get("location")
            if not location:
                logger.warning("fetch_page: redirect without location from %s", current_url)
                return ""
            current_url = urljoin(current_url, location)
            if not is_public_http_url(current_url):
                logger.warning("fetch_page: refusing unsafe redirect target: %s", current_url)
                return ""
        else:
            logger.warning("fetch_page: too many redirects from %s", url)
            return ""
        resp.raise_for_status()
        html = resp.text
        html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as error:
        logger.debug("fetch_page failed for %s: %s", url, error)
        return ""


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """
    Search the web using DuckDuckGo. No API key required.
    Returns list of dicts with: title, url, snippet.
    """
    from gcrm.tools.costs import record_search
    record_search(1)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        logger.info("web_search: %d results for '%s'", len(results), query)
        return [{"title": entry.get("title", ""), "url": entry.get("href", ""), "snippet": entry.get("body", "")} for entry in results]
    except Exception as error:
        logger.warning("web_search failed for '%s': %s", query, error)
        return []


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "engcrm-city-normalizer/1.0 (+https://engcrm.christopherrehm.de)"
_PLACE_TYPES = {"city", "town", "village", "municipality", "administrative"}


def normalize_city(name: str, country: str = "DE", limit: int = 4) -> list[dict]:
    """
    Canonicalize a city name via Nominatim (OpenStreetMap) — free, no API key.
    Expands variants ('Landsberg' -> 'Landsberg am Lech'), fixes umlauts
    ('Munchen' -> 'München'), and returns [] for a name it can't place (likely a
    typo). Each candidate is {name, state, type}, best match first.
    """
    name = (name or "").strip()
    if not name:
        return []
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={
                "q": name,
                "countrycodes": country.lower(),
                "format": "jsonv2",
                "limit": limit,
                "addressdetails": 1,
            },
            headers={"User-Agent": NOMINATIM_UA},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as error:
        logger.warning("normalize_city failed for %r: %s", name, error)
        return []

    candidates: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("addresstype") not in _PLACE_TYPES:
            continue
        address = row.get("address", {})
        canonical = (
            address.get("city") or address.get("town") or address.get("village")
            or address.get("municipality") or row.get("name", "")
        )
        if not canonical or canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        candidates.append({
            "name": canonical,
            "state": address.get("state", ""),
            "type": row.get("addresstype", ""),
        })
    return candidates


def geocode(query: str, country: str = "DE") -> tuple[float, float] | None:
    """Geocode a free-text address (or business name + city) via Nominatim (OSM,
    free, no key). Returns (latitude, longitude), or None if not found. Callers
    must rate-limit to ~1 request/second per Nominatim's usage policy."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "countrycodes": country.lower(), "format": "jsonv2", "limit": 1},
            headers={"User-Agent": NOMINATIM_UA},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as error:
        logger.warning("geocode failed for %r: %s", query, error)
        return None
    if not rows:
        return None
    try:
        return float(rows[0]["lat"]), float(rows[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None
