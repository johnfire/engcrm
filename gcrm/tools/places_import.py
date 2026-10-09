"""Add the results of one Google Maps search as organizations.

The same search you would type into Google Maps ("Weiterbildung" near
"Augsburg"), run through the Places API: up to 60 places, each with its website,
phone and coordinates. Each place is filed under the town it is actually in,
read from its address, not the town searched for — a search "in Augsburg"
returns Königsbrunn and Friedberg too, and people take their company's city.

Places Google marks as permanently closed are skipped. Duplicates are left to
save_organization, which skips a known (name, city) or email.

A list copied by hand from the Google Maps results panel can be imported too
(parse_maps_copy): it carries name, category, street and phone, but not the
website, so each entry is matched to its Places record by phone number.
"""
import re

from gcrm.sources import MAPS_IMPORT
from gcrm.tools.company_places import describe_place
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.search import google_maps_search

CLOSED = "CLOSED_PERMANENTLY"


def to_organization(result: dict) -> dict | None:
    """One google_maps_search result as save_organization arguments, or None
    for a place that is permanently closed or has no name."""
    if result.get("business_status") == CLOSED or not result.get("name"):
        return None
    place = describe_place(result.get("google_data") or {})
    return {
        "name": result["name"].strip(),
        "city": place["city"] or result.get("city", ""),
        "country": place["country"] or result.get("country", "DE"),
        "address": result.get("address", ""),
        "website": result.get("website", ""),
        "phone": result.get("phone", ""),
        "google": result,
    }


def search(query: str, near: str, country: str = "DE") -> list[dict]:
    """The organizations a Maps search would add (billed: up to 3 Places requests)."""
    found = (to_organization(r) for r in google_maps_search(query, near, country, pages=3))
    return [org for org in found if org]


def add_organizations(organizations: list[dict], type: str, note: str) -> dict:
    """Save each one as a candidate. Returns {created: [ids], duplicates: [names]}."""
    created, duplicates = [], []
    for org in organizations:
        contact_id = save_organization(
            org["name"], org["city"], country=org["country"], type=type,
            website=org["website"], phone=org["phone"],
            notes=f"{note}\n{org['address']}".strip(), google=org["google"], source=MAPS_IMPORT,
        )
        if contact_id:
            created.append(contact_id)
        else:
            duplicates.append(org["name"])
    return {"created": created, "duplicates": duplicates}


_PHONE = re.compile(r"(\+?\d[\d ]{5,}\d)\s*$")
_NOT_A_CATEGORY = ("Open", "Closed", "Opens", "Geöffnet", "Geschlossen")


def parse_maps_copy(text: str) -> list[dict]:
    """Entries from text copied out of the Google Maps results panel. Each card
    starts with its name twice (with "Sponsored" in between for an ad), then the
    rating, a "Category · Street" line, and an opening-hours line ending in the
    phone. Returns {name, category, street, phone, sponsored}, one per name."""
    lines = [line.strip() for line in text.splitlines()]
    entries, seen = [], set()
    for i, line in enumerate(lines[:-1]):
        if not line:
            continue
        if lines[i + 1] == line:
            start, sponsored = i + 2, False
        elif lines[i + 1] == "Sponsored" and i + 3 < len(lines) and lines[i + 3] == line:
            start, sponsored = i + 4, True
        else:
            continue
        if line in seen:
            continue
        seen.add(line)
        entries.append({"name": line, "sponsored": sponsored, **_card_details(lines[start:start + 6])})
    return entries


def _card_details(card: list[str]) -> dict:
    category = street = phone = ""
    for line in card:
        if line in ("Website", "Directions"):
            break
        parts = [part.strip() for part in line.split("·") if part.strip()]
        if not category and len(parts) >= 2 and not line.startswith(_NOT_A_CATEGORY):
            category, street = parts[0], parts[-1]
        elif match := _PHONE.search(line):
            phone = match.group(1)
    return {"category": category, "street": street, "phone": phone}


def phone_digits(phone: str) -> str:
    """Digits only, national form (+49 821 … and 0821 … compare equal)."""
    digits = re.sub(r"\D", "", phone or "")
    return "0" + digits[2:] if digits.startswith("49") else digits


def match_copied_entry(entry: dict, near: str, country: str = "DE", lookup=google_maps_search) -> dict:
    """The organization for one copied entry: its Places record when one with the
    same phone number is found (adds website, coordinates and real town), else
    just what was copied. One billed Places request."""
    query = f"{entry['name']} {entry['street']}".strip()
    wanted = phone_digits(entry["phone"])
    for result in lookup(query, near, country, pages=1):
        organization = to_organization(result)
        if organization and wanted and phone_digits(result.get("phone", "")) == wanted:
            return {**organization, "name": entry["name"], "matched": True}
    return {"name": entry["name"], "city": near, "country": country, "address": entry["street"],
            "website": "", "phone": entry["phone"], "google": None, "matched": False}
