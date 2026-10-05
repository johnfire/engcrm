"""
Give every person with no city the city of the company they work for
(see gcrm/tools/people_city.py). Previews by default.

    uv run python scripts/people_city_from_company.py            # preview
    uv run python scripts/people_city_from_company.py --apply    # fill blanks

People whose city differs from their company's are listed but never changed.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.tools.people_city import fill_blank_cities, survey  # noqa: E402


def _table(rows: list[dict], with_person_city: bool) -> None:
    for r in rows:
        person = f" | person city: {r['city']!s:<22}" if with_person_city else ""
        print(f"  #{r['id']:<5} {r['name'][:28]:<28} | {r['company'][:30]:<30} -> "
              f"{r['company_city'] or '—'!s:<20} ({r['company_country'] or '?'})"
              f"{person} | source: {r['source'] or '—'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="fill the blank cities (default: preview)")
    args = parser.parse_args()

    report = survey()
    print(f"\nWOULD FILL — no city, company has one ({len(report['fill'])}):")
    _table(report["fill"], with_person_city=False)
    print(f"\nMISMATCH — person city differs from company, NOT changed ({len(report['mismatch'])}):")
    _table(report["mismatch"], with_person_city=True)
    print(f"\nCANNOT FILL — company has no city either ({len(report['company_has_no_city'])}):")
    _table(report["company_has_no_city"], with_person_city=False)
    print(f"\nAlready the same city: {report['same']}")
    print(f"No city and not linked to any company: {report['unlinked_without_city']}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to fill the blanks.")
        return 0
    updated = fill_blank_cities([r["id"] for r in report["fill"]])
    print(f"\nAPPLIED — filled {updated} of {len(report['fill'])}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
