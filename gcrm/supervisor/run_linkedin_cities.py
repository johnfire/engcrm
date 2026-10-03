"""Find the city of the organizations created from LinkedIn employers.

The LinkedIn export has no location, so each company name is looked up once in
Google Places (only the company name is sent). A city is accepted only when
exactly one place carries the company's name; anything else — a chain in several
cities, an unknown company — is left for you in the review queue. Every outcome
is cached, so no company is ever looked up (and billed) twice.

Default is a dry run: it only counts the lookups it would make.

Usage:
    uv run python -m gcrm.supervisor.run_linkedin_cities               # count only
    uv run python -m gcrm.supervisor.run_linkedin_cities --apply --limit 25
    uv run python -m gcrm.supervisor.run_linkedin_cities --apply        # up to 200
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 200
# Rough list price for a Places text search with address fields. An estimate from
# memory of Google's published pricing, which changes — check your billing
# console; a monthly free allowance may make the real cost zero.
ESTIMATED_USD_PER_1000 = 35


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="Make the lookups (default: count only)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Most lookups this run (default {DEFAULT_LIMIT})")
    args = parser.parse_args()

    from gcrm.tools.db_linkedin import count_city_work, resolve_company_cities

    work = count_city_work()
    planned = min(work["to_lookup"], args.limit)
    print(f"companies never looked up : {work['to_lookup']}")
    print(f"accepted city to apply    : {work['cached_ready']} (already cached, free)")
    print(f"lookups this run          : {planned}  (limit {args.limit})")
    print(f"estimated list-price cost : ~${planned * ESTIMATED_USD_PER_1000 / 1000:.2f} "
          "(estimate — see comment in this file)")
    if not args.apply:
        print("\ncount only — nothing sent. Re-run with --apply to make the lookups.")
        return
    counts = resolve_company_cities(limit=args.limit)
    print(f"\nresult: {counts}")
    if counts["stopped"]:
        print(f"STOPPED EARLY: {counts['stopped']}")


if __name__ == "__main__":
    main()
