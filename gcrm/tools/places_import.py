"""Add the results of one Google Maps search as organizations.

The same search you would type into Google Maps ("Weiterbildung" near
"Augsburg"), run through the Places API: up to 60 places, each with its website,
phone and coordinates. Each place is filed under the town it is actually in,
read from its address, not the town searched for — a search "in Augsburg"
returns Königsbrunn and Friedberg too, and people take their company's city.

Places Google marks as permanently closed are skipped. Duplicates are left to
save_organization, which skips a known (name, city) or email.
"""
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
            notes=f"{note}\n{org['address']}".strip(), google=org["google"],
        )
        if contact_id:
            created.append(contact_id)
        else:
            duplicates.append(org["name"])
    return {"created": created, "duplicates": duplicates}
