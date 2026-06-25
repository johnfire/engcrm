"""
Backfill Google Places data (coords + status/rating + the full payload) onto
contacts saved before geo capture existed. One Google Text Search per contact
(name + city, single page), then update. Idempotent — only touches contacts with
no google_data, and only writes when the top match's name is similar enough to
avoid grabbing the wrong business.

Usage:
    uv run python -m gcrm.supervisor.run_google_backfill
    uv run python -m gcrm.supervisor.run_google_backfill --limit 50
"""
import argparse
import logging
import time
from difflib import SequenceMatcher

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def _similar(left: str, right: str) -> float:
    return SequenceMatcher(None, (left or "").lower(), (right or "").lower()).ratio()


def main():
    parser = argparse.ArgumentParser(description="Backfill Google Places data onto contacts")
    parser.add_argument("--limit", type=int, default=None, help="Max contacts to process this run")
    args = parser.parse_args()

    from gcrm.db.connection import db
    from gcrm.tools.db import update_contact_google_data
    from gcrm.tools.search import google_maps_search

    with db() as conn:
        cur = conn.cursor()
        sql = "SELECT id, name, city, country FROM contacts WHERE google_data IS NULL AND name <> '' ORDER BY id"
        if args.limit:
            sql += " LIMIT %s"
            cur.execute(sql, (args.limit,))
        else:
            cur.execute(sql)
        rows = cur.fetchall()

    logger.info("google backfill: %d contact(s) without google_data", len(rows))
    updated = 0
    for index, row in enumerate(rows, 1):
        city = row.get("city") or ""
        try:
            matches = google_maps_search(row["name"], city, row.get("country") or "DE", pages=1)
        except Exception as error:
            logger.warning("google backfill: lookup failed for %s — %s", row["name"], error)
            matches = []
        if matches and _similar(row["name"], matches[0].get("name", "")) >= 0.5:
            update_contact_google_data(row["id"], matches[0])
            updated += 1
        if index % 25 == 0:
            logger.info("  ... %d/%d processed, %d updated", index, len(rows), updated)
        time.sleep(0.2)  # gentle pacing on the Google API

    logger.info("google backfill done: %d of %d updated", updated, len(rows))


if __name__ == "__main__":
    main()
