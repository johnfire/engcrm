"""
Add organizations from Google Maps (see gcrm/tools/places_import.py), either by
running a search or from a results list copied out of the Maps panel. Previews
by default; --apply saves them as candidates.

    # run a Maps search through the Places API (up to 3 billed requests, 60 places)
    uv run python scripts/import_places_search.py "Weiterbildung" Augsburg
    uv run python scripts/import_places_search.py "Weiterbildung" Augsburg --apply

    # a list copied from the Maps panel ("-" reads stdin). The preview is free; --apply
    # makes one billed Places request per entry to add its website and location
    uv run python scripts/import_places_search.py "Weiterbildung" Augsburg --from-copy list.txt \\
        --exclude "beINsure - unabhängige Finanzberatung" --apply

New organizations are typed with --type (default: the query).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.tools.places_import import (  # noqa: E402
    add_organizations,
    match_copied_entry,
    parse_maps_copy,
    search,
)


def _from_copy(path: str, near: str, exclude: set[str], apply: bool) -> list[dict] | None:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    entries = [e for e in parse_maps_copy(text) if e["name"] not in exclude]
    print(f"{len(entries)} entries copied from Maps (excluded: {', '.join(sorted(exclude)) or '—'}):\n")
    for e in entries:
        ad = "AD " if e["sponsored"] else "   "
        print(f"  {ad}{e['name'][:50]:<50} | {e['category'][:24]:<24} | {e['street'][:28]:<28} | {e['phone'] or '—'}")
    if not apply:
        return None
    organizations = []
    for e in entries:
        organization = match_copied_entry(e, near)
        organization["address"] = f"{e['category']} · {organization['address']}".strip(" ·")
        organizations.append(organization)
    unmatched = [o["name"] for o in organizations if not o["matched"]]
    print(f"\nmatched to Google Places by phone: {len(organizations) - len(unmatched)}; "
          f"saved from the copy only: {len(unmatched)} {unmatched}")
    return organizations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help='what to search for, e.g. "Weiterbildung"')
    parser.add_argument("near", help="the town to search around, e.g. Augsburg")
    parser.add_argument("--type", default="", help="organization type to record (default: the query)")
    parser.add_argument("--from-copy", metavar="FILE", help='a list copied from the Maps panel ("-" for stdin)')
    parser.add_argument("--exclude", action="append", default=[], help="an entry name to leave out (repeatable)")
    parser.add_argument("--apply", action="store_true", help="save them (default: preview only)")
    args = parser.parse_args()

    if args.from_copy:
        organizations = _from_copy(args.from_copy, args.near, set(args.exclude), args.apply)
        source = f"copied from a Google Maps search '{args.query}' near {args.near}"
    else:
        organizations = search(args.query, args.near)
        print(f"{len(organizations)} places for {args.query!r} near {args.near}:\n")
        for org in organizations:
            print(f"  {org['name'][:55]:<55} | {org['city'][:18]:<18} | {org['website'] or '—'}")
        organizations = organizations if args.apply else None
        source = f"found by Google Maps search '{args.query}' near {args.near}"
    if organizations is None:
        print("\nDRY RUN — nothing saved. Re-run with --apply to add them (known ones are skipped).")
        return 0

    result = add_organizations(organizations, type=args.type or args.query, note=f"{source[0].upper()}{source[1:]}.")
    print(f"\nAPPLIED — {len(result['created'])} added, {len(result['duplicates'])} already known: "
          f"{', '.join(result['duplicates']) or '—'}")
    print(f"new ids: {result['created']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
