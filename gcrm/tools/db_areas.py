"""Area scan database operations — the map-pick / GPS-radius counterpart to
db_cities.py. See docs/plans/2026-08-20-area-scanning-design.md."""
from gcrm.db.connection import db, serialize_row
from gcrm.vertical import SCAN_LEVELS
from gcrm.workspace_context import get_workspace_id

# An existing area is reused if a saved point is within this distance and has
# the same radius, so repeat "scan here" taps don't spawn duplicate rows.
_REUSE_DISTANCE_M = 50


def _distance_m_sql(lat1: str, lon1: str, lat2: str, lon2: str) -> str:
    """Great-circle distance in meters between two points, each given as a raw
    SQL expression — a column reference (e.g. 'sa.latitude') or a '%s'
    placeholder for a bound parameter. Callers own supplying matching bind
    params, in the order '%s' appears in the returned text (lat1, lon1, lat1
    when both point-1 args are placeholders)."""
    return (
        "6371000 * acos(LEAST(1, GREATEST(-1, "
        f"cos(radians({lat1})) * cos(radians({lat2})) * cos(radians({lon2}) - radians({lon1})) "
        f"+ sin(radians({lat1})) * sin(radians({lat2})))))"
    )


def find_or_create_area(
    lat: float,
    lon: float,
    radius_m: int,
    label: str = "",
    city_id: int | None = None,
    created_by: int | None = None,
) -> int:
    """Return the id of an existing nearby-and-same-radius area, or create one."""
    dist = _distance_m_sql("%s", "%s", "latitude", "longitude")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id FROM scan_areas
            WHERE radius_m = %s AND ({dist}) < %s
            ORDER BY ({dist}) ASC
            LIMIT 1
            """,
            (radius_m, lat, lon, lat, _REUSE_DISTANCE_M, lat, lon, lat),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            """
            INSERT INTO scan_areas (label, latitude, longitude, radius_m, city_id, workspace_id, created_by)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default')), %s)
            RETURNING id
            """,
            (label or None, lat, lon, radius_m, city_id, get_workspace_id(), created_by),
        )
        return cur.fetchone()["id"]


def get_area(area_id: int) -> dict | None:
    """Return a single area's fields plus its resolved city/country (via
    city_id), or None if it doesn't exist."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sa.*, ci.city, ci.country
            FROM scan_areas sa
            LEFT JOIN cities ci ON ci.id = sa.city_id
            WHERE sa.id = %s
            """,
            (area_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        row = dict(row)
        row["latitude"] = float(row["latitude"])
        row["longitude"] = float(row["longitude"])
        return serialize_row(row)


def get_all_area_scan_status() -> list[dict]:
    """Return all areas with their scan status across all levels, plus how many
    saved contacts currently fall within each area's radius."""
    live_dist = _distance_m_sql("sa.latitude", "sa.longitude", "co.latitude", "co.longitude")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                sa.id, sa.label, sa.latitude, sa.longitude, sa.radius_m,
                sa.city_id, sa.created_at,
                ci.city, ci.country,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'level', ascan.level,
                            'last_run_at', ascan.last_run_at,
                            'organizations_found', ascan.organizations_found,
                            'run_count', ascan.run_count,
                            'complete', ascan.complete
                        ) ORDER BY ascan.level
                    ) FILTER (WHERE ascan.level IS NOT NULL),
                    '[]'
                ) AS scans,
                COALESCE(live.cnt, 0) AS total_contacts
            FROM scan_areas sa
            LEFT JOIN cities ci ON ci.id = sa.city_id
            LEFT JOIN area_scans ascan ON ascan.area_id = sa.id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM contacts co
                WHERE co.latitude IS NOT NULL AND co.longitude IS NOT NULL
                  AND co.deleted_at IS NULL
                  AND ({live_dist}) < sa.radius_m
            ) live ON TRUE
            GROUP BY sa.id, sa.label, sa.latitude, sa.longitude, sa.radius_m,
                     sa.city_id, sa.created_at, ci.city, ci.country, live.cnt
            ORDER BY sa.created_at DESC
            """,
        )
        rows = []
        for row in cur.fetchall():
            row = dict(row)
            row["latitude"] = float(row["latitude"])
            row["longitude"] = float(row["longitude"])
            rows.append(serialize_row(row))
        return rows


def build_area_overview() -> dict:
    """Shape the per-area scan-status list plus headline stats — the area
    equivalent of build_research_overview(), for the web areas page and the
    mobile area-scan screen to share."""
    areas = get_all_area_scan_status()
    for area in areas:
        scans_by_level = {scan["level"]: scan for scan in (area.get("scans") or [])}
        area["scanned_levels"] = sorted(scans_by_level.keys())
    return {
        "areas": areas,
        "levels": list(SCAN_LEVELS.keys()),
        "level_labels": {lvl: cfg["label"] for lvl, cfg in SCAN_LEVELS.items()},
        "total": len(areas),
    }


def record_area_scan_result(area_id: int, level: int, organizations_found: int, complete: bool = False) -> None:
    """Record the result of a completed area scan. Creates or updates the
    area_scans row. `complete` is True once a scan turns up no new businesses
    for the level. Mirrors db_cities.record_scan_result."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO area_scans (area_id, level, last_run_at, organizations_found, run_count, complete)
            VALUES (%s, %s, NOW(), %s, 1, %s)
            ON CONFLICT (area_id, level) DO UPDATE
                SET last_run_at = NOW(),
                    organizations_found = area_scans.organizations_found + EXCLUDED.organizations_found,
                    run_count = area_scans.run_count + 1,
                    complete = EXCLUDED.complete
            """,
            (area_id, level, organizations_found, complete),
        )


def get_area_organizations(area_id: int, limit: int = 500) -> list[dict]:
    """Return contacts currently within the area's radius, nearest first — for
    the map-pins results view. Computed live from contacts.latitude/longitude
    rather than a stored join, so it stays correct as contacts move through
    the pipeline or get deleted."""
    dist = _distance_m_sql("sa.latitude", "sa.longitude", "co.latitude", "co.longitude")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT co.id, co.name, co.type, co.pipeline_stage, co.status,
                   co.latitude, co.longitude, co.website,
                   ({dist}) AS distance_m
            FROM contacts co
            JOIN scan_areas sa ON sa.id = %s
            WHERE co.latitude IS NOT NULL AND co.longitude IS NOT NULL
              AND co.deleted_at IS NULL
              AND ({dist}) < sa.radius_m
            ORDER BY distance_m ASC
            LIMIT %s
            """,
            (area_id, limit),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]
