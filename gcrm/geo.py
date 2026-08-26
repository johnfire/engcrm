"""Distance-from-home calculations. Home is Chris's base in Klosterlechfeld,
Bavaria — resolved once via Nominatim (see gcrm.tools.search.geocode) and
hardcoded here since it never changes."""

HOME_LAT = 48.1588074
HOME_LON = 10.8309762


def distance_km_sql(lat_col: str, lon_col: str) -> str:
    """Great-circle distance in km from HOME_LAT/HOME_LON to the point named by
    `lat_col`/`lon_col` — each a raw SQL expression (column reference or
    COALESCE(...)). Home coordinates are inlined as literals since they're a
    fixed constant, not user input, so no bind params are needed.

    Explicitly NULL when either coordinate is missing — Postgres's LEAST/
    GREATEST silently ignore a NULL argument rather than propagating it, so
    without this guard a missing coordinate would come out as acos(-1), the
    ~20015km antipodal distance, instead of unknown."""
    return (
        f"CASE WHEN {lat_col} IS NULL OR {lon_col} IS NULL THEN NULL ELSE "
        "6371 * acos(LEAST(1, GREATEST(-1, "
        f"cos(radians({HOME_LAT})) * cos(radians({lat_col})) * cos(radians({lon_col}) - radians({HOME_LON})) "
        f"+ sin(radians({HOME_LAT})) * sin(radians({lat_col}))))) END"
    )
