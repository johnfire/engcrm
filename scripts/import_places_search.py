"""
Add the results of a Google Maps search as organizations
(see gcrm/tools/places_import.py). Previews by default; --apply saves them.

    uv run python scripts/import_places_search.py "Weiterbildung" Augsburg
    uv run python scripts/import_places_search.py "Weiterbildung" Augsburg --apply

Each run makes up to 3 billed Places requests (up to 60 places). New
organizations start as candidates, typed with --type (default: the query).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.tools.places_import import add_organizations, search  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help='what to search for, e.g. "Weiterbildung"')
    parser.add_argument("near", help="the town to search around, e.g. Augsburg")
    parser.add_argument("--type", default="", help="organization type to record (default: the query)")
    parser.add_argument("--apply", action="store_true", help="save them (default: preview only)")
    args = parser.parse_args()

    organizations = search(args.query, args.near)
    print(f"{len(organizations)} places for {args.query!r} near {args.near}:\n")
    for org in organizations:
        print(f"  {org['name'][:55]:<55} | {org['city'][:18]:<18} | {org['website'] or '—'}")
    if not args.apply:
        print("\nDRY RUN — nothing saved. Re-run with --apply to add them (known ones are skipped).")
        return 0

    note = f"Found by Google Maps search '{args.query}' near {args.near}."
    result = add_organizations(organizations, type=args.type or args.query, note=note)
    print(f"\nAPPLIED — {len(result['created'])} added, {len(result['duplicates'])} already known: "
          f"{', '.join(result['duplicates']) or '—'}")
    print(f"new ids: {result['created']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
