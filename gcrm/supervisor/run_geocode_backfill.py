"""
One-time backfill: geocode contacts saved before lat/long capture existed.

Uses Nominatim (OSM, free), rate-limited to ~1 request/second per their usage
policy, so a few hundred contacts take a few minutes. Idempotent — only touches
contacts with no coordinates, so it is safe to re-run.

Usage:
    uv run python -m gcrm.supervisor.run_geocode_backfill
    uv run python -m gcrm.supervisor.run_geocode_backfill --limit 50
"""
import argparse
import logging
import time

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Geocode contacts missing lat/long via Nominatim")
    parser.add_argument("--limit", type=int, default=None, help="Max contacts to process this run")
    args = parser.parse_args()

    from gcrm.db.connection import db
    from gcrm.tools.search import geocode

    with db() as conn:
        cur = conn.cursor()
        sql = "SELECT id, name, address, city, country FROM contacts WHERE latitude IS NULL ORDER BY id"
        if args.limit:
            sql += " LIMIT %s"
            cur.execute(sql, (args.limit,))
        else:
            cur.execute(sql)
        rows = cur.fetchall()

    logger.info("geocode backfill: %d contact(s) without coordinates", len(rows))
    geocoded = 0
    for index, row in enumerate(rows, 1):
        query = (row.get("address") or "").strip() or f"{row['name']} {row.get('city') or ''}".strip()
        coords = geocode(query, row.get("country") or "DE")
        if coords:
            with db() as conn:
                conn.cursor().execute(
                    "UPDATE contacts SET latitude = %s, longitude = %s WHERE id = %s",
                    (coords[0], coords[1], row["id"]),
                )
            geocoded += 1
        if index % 25 == 0:
            logger.info("  ... %d/%d processed, %d geocoded", index, len(rows), geocoded)
        time.sleep(1.1)  # Nominatim: max ~1 request/second

    logger.info("geocode backfill done: %d of %d geocoded", geocoded, len(rows))


if __name__ == "__main__":
    main()
