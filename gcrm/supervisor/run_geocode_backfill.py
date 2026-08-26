"""
One-time backfill: geocode contacts and people saved before lat/long capture
existed for their table (contacts: migration 028; people: migration 050).

Uses Nominatim (OSM, free), rate-limited to ~1 request/second per their usage
policy, so a few hundred rows take a few minutes. Idempotent — only touches
rows with no coordinates, so it is safe to re-run.

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


def _backfill(table: str, query_sql: str, row_to_query, args):
    from gcrm.db.connection import db
    from gcrm.tools.search import geocode

    with db() as conn:
        cur = conn.cursor()
        sql = query_sql
        if args.limit:
            sql += " LIMIT %s"
            cur.execute(sql, (args.limit,))
        else:
            cur.execute(sql)
        rows = cur.fetchall()

    logger.info("geocode backfill: %d %s(s) without coordinates", len(rows), table)
    geocoded = 0
    for index, row in enumerate(rows, 1):
        coords = geocode(row_to_query(row), row.get("country") or "DE")
        if coords:
            with db() as conn:
                conn.cursor().execute(
                    f"UPDATE {table} SET latitude = %s, longitude = %s WHERE id = %s",
                    (coords[0], coords[1], row["id"]),
                )
            geocoded += 1
        if index % 25 == 0:
            logger.info("  ... %d/%d processed, %d geocoded", index, len(rows), geocoded)
        time.sleep(1.1)  # Nominatim: max ~1 request/second

    logger.info("geocode backfill done: %d of %d %s(s) geocoded", geocoded, len(rows), table)


def main():
    parser = argparse.ArgumentParser(description="Geocode contacts/people missing lat/long via Nominatim")
    parser.add_argument("--limit", type=int, default=None, help="Max rows per table this run")
    args = parser.parse_args()

    _backfill(
        "contacts",
        "SELECT id, name, address, city, country FROM contacts WHERE latitude IS NULL ORDER BY id",
        lambda row: (row.get("address") or "").strip() or f"{row['name']} {row.get('city') or ''}".strip(),
        args,
    )
    # A person's name isn't a geocodable location — city alone is the query.
    _backfill(
        "people",
        "SELECT id, city, country FROM people WHERE latitude IS NULL AND city IS NOT NULL ORDER BY id",
        lambda row: row.get("city") or "",
        args,
    )


if __name__ == "__main__":
    main()
