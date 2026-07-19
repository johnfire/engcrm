from typing import TypedDict


class ResearchState(TypedDict):
    # --- inputs ---
    city: str
    country: str  # ISO 3166-1 alpha-2, default "DE"
    level: int  # scan level 1-5

    # --- working state ---
    run_id: int
    maps_terms: list[str]  # fixed terms for this level
    raw_results: list[dict]  # from Google Maps + web search + fetched pages
    contacts_to_save: list[dict]
    saved_ids: list[int]
    errors: list[str]

    # --- incremental scan ---
    new_found: int  # businesses found that aren't yet saved for this city
    scan_complete: bool  # True when this pass covered all remaining businesses
    google_by_name: dict  # lowercased name -> full Google place dict

    # --- output ---
    summary: str
