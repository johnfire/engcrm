from typing import TypedDict


class ResearchState(TypedDict):
    # --- inputs ---
    city: str
    country: str  # ISO 3166-1 alpha-2, default "DE"
    levels: list[int]  # scan levels, 1-10; a city scan passes a single-item list

    # --- area/GPS-radius scan inputs (unset for a plain city scan) ---
    area_id: int | None
    latitude: float | None
    longitude: float | None
    radius_m: int | None

    # --- working state ---
    run_id: int
    maps_terms: list[str]  # union of terms across all requested levels
    raw_results: list[dict]  # from Google Maps + web search + fetched pages
    organizations_to_save: list[dict]
    saved_ids: list[int]
    errors: list[str]

    # --- incremental scan ---
    new_found: int  # businesses found that aren't yet saved for this city
    scan_complete: bool  # True when this pass covered all remaining businesses
    google_by_name: dict  # lowercased name -> full Google place dict

    # --- output ---
    summary: str
