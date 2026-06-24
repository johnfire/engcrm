"""City master-list and per-city scan-level database operations."""
from gcrm.db.connection import db


def get_cities(country: str = "") -> list[dict]:
    """Return all cities, optionally filtered by country."""
    with db() as conn:
        cur = conn.cursor()
        if country:
            cur.execute(
                "SELECT * FROM cities WHERE country = %s ORDER BY city",
                (country,),
            )
        else:
            cur.execute("SELECT * FROM cities ORDER BY city, country")
        return [dict(row) for row in cur.fetchall()]


def get_city_market_context(city: str, country: str = "DE") -> dict:
    """Return market_character and market_notes for a city. Returns empty dict if not found."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT market_character, market_notes FROM cities WHERE lower(city) = lower(%s) AND country = %s",
            (city, country.upper()),
        )
        row = cur.fetchone()
        return dict(row) if row else {"market_character": "unknown", "market_notes": ""}


def update_city_market(city: str, country: str = "DE", character: str = "", notes: str = "") -> bool:
    """Update market_character and/or market_notes for a city. Returns True if found."""
    with db() as conn:
        cur = conn.cursor()
        if character and notes:
            cur.execute(
                "UPDATE cities SET market_character = %s, market_notes = %s WHERE lower(city) = lower(%s) AND country = %s",
                (character, notes, city, country.upper()),
            )
        elif character:
            cur.execute(
                "UPDATE cities SET market_character = %s WHERE lower(city) = lower(%s) AND country = %s",
                (character, city, country.upper()),
            )
        elif notes:
            cur.execute(
                "UPDATE cities SET market_notes = %s WHERE lower(city) = lower(%s) AND country = %s",
                (notes, city, country.upper()),
            )
        return cur.rowcount > 0


def add_city(city: str, country: str = "DE", region: str = "") -> int:
    """Add a city to the master list. Returns city_id. Safe to call if already exists."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cities (city, country, region)
            VALUES (%s, %s, %s)
            ON CONFLICT (city, country) DO UPDATE SET region = EXCLUDED.region
            RETURNING id
            """,
            (city, country, region),
        )
        return cur.fetchone()["id"]


def get_city_scan_status(city: str, country: str = "DE") -> list[dict]:
    """Return scan records for a city across all levels."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cs.level, cs.last_run_at, cs.contacts_found, cs.run_count, cs.due_for_rerun
            FROM city_scans cs
            JOIN cities ci ON ci.id = cs.city_id
            WHERE LOWER(ci.city) = LOWER(%s) AND ci.country = %s
            ORDER BY cs.level
            """,
            (city, country),
        )
        return [dict(row) for row in cur.fetchall()]


def get_all_city_scan_status() -> list[dict]:
    """Return all cities with their scan status across all levels."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                ci.id, ci.city, ci.country, ci.region,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'level', cs.level,
                            'last_run_at', cs.last_run_at,
                            'contacts_found', cs.contacts_found,
                            'run_count', cs.run_count,
                            'due_for_rerun', cs.due_for_rerun,
                            'complete', cs.complete
                        ) ORDER BY cs.level
                    ) FILTER (WHERE cs.level IS NOT NULL),
                    '[]'
                ) AS scans,
                COALESCE(
                    json_object_agg(emailed.scan_level::text, emailed.cnt)
                        FILTER (WHERE emailed.scan_level IS NOT NULL),
                    '{}'
                ) AS emailed_by_level,
                COALESCE(live.cnt, 0) AS total_contacts
            FROM cities ci
            LEFT JOIN city_scans cs ON cs.city_id = ci.id
            LEFT JOIN (
                SELECT lower(city) AS city_lower, scan_level, COUNT(*) AS cnt
                FROM contacts
                WHERE status IN ('contacted', 'meeting', 'proposal', 'accepted')
                  AND scan_level IS NOT NULL
                GROUP BY lower(city), scan_level
            ) emailed ON lower(ci.city) = emailed.city_lower
            LEFT JOIN (
                SELECT lower(city) AS city_lower, COUNT(*) AS cnt
                FROM contacts
                GROUP BY lower(city)
            ) live ON lower(ci.city) = live.city_lower
            GROUP BY ci.id, ci.city, ci.country, ci.region, live.cnt
            ORDER BY ci.city, ci.country
            """,
        )
        return [dict(row) for row in cur.fetchall()]


def record_scan_result(city: str, country: str, level: int, contacts_found: int, complete: bool = False) -> None:
    """Record the result of a completed scan. Creates or updates the city_scans row.
    `complete` is True once a scan turns up no new businesses for the level."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM cities WHERE LOWER(city) = LOWER(%s) AND country = %s", (city, country))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO cities (city, country) VALUES (%s, %s) RETURNING id",
                (city, country),
            )
            row = cur.fetchone()
        city_id = row["id"]
        cur.execute(
            """
            INSERT INTO city_scans (city_id, level, last_run_at, contacts_found, run_count, complete)
            VALUES (%s, %s, NOW(), %s, 1, %s)
            ON CONFLICT (city_id, level) DO UPDATE
                SET last_run_at = NOW(),
                    contacts_found = city_scans.contacts_found + EXCLUDED.contacts_found,
                    run_count = city_scans.run_count + 1,
                    due_for_rerun = FALSE,
                    complete = EXCLUDED.complete
            """,
            (city_id, level, contacts_found, complete),
        )


def can_run_level(city: str, country: str, level: int) -> tuple[bool, str]:
    """
    Check if a scan level can be run on a city.
    Level 1 can always run. All others require level 1 to be completed first.
    Returns (allowed, reason).
    """
    if level == 1:
        return True, ""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cs.level FROM city_scans cs
            JOIN cities ci ON ci.id = cs.city_id
            WHERE LOWER(ci.city) = LOWER(%s) AND ci.country = %s AND cs.level = 1
            """,
            (city, country),
        )
        if not cur.fetchone():
            return False, f"Level 1 must be run on {city} first"
    return True, ""
