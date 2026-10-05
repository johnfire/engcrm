"""
Merge a duplicate person into the one that stays (see gcrm/tools/people_merge.py
for the rules). Previews by default; nothing is written without --apply.

    uv run python scripts/merge_people.py 57 182                          # preview
    uv run python scripts/merge_people.py 57 182 --apply --backup FILE    # merge

The full before-image (both people and every moved row) is printed as JSON and,
with --backup, written to FILE, so the merge can be undone by hand.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.tools.people_merge import MergeRefused, merge_people  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("keep_id", type=int, help="the person that stays")
    parser.add_argument("drop_id", type=int, help="the duplicate, merged in and then deleted")
    parser.add_argument("--apply", action="store_true", help="write the merge (default: preview only)")
    parser.add_argument("--backup", type=Path, help="write the before-image JSON here")
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error("--apply needs --backup FILE so the merge can be undone")

    try:
        report = merge_people(args.keep_id, args.drop_id, apply=args.apply)
    except MergeRefused as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 1

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.backup:
        args.backup.write_text(text, encoding="utf-8")
    print(text)
    print("APPLIED" if args.apply else "DRY RUN — nothing written. Re-run with --apply --backup FILE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
