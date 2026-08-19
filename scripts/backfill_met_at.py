"""
Move meeting places out of people.notes and into people.met_at.

Before met_at existed, the only place to record where someone was met was the
free-text notes field. This copies those notes across. It cannot tell a meeting
place ("aux theatre viertel art show") from a genuine note, so it previews by
default and only touches the rows you name.

Usage:
    # 1. See the candidates — rows with notes and no met_at yet. Changes nothing.
    uv run python scripts/backfill_met_at.py

    # 2. Copy notes -> met_at for the rows you picked (notes are kept).
    uv run python scripts/backfill_met_at.py --ids 12,15,18 --apply

    # 3. Same, but also blank the notes it copied from.
    uv run python scripts/backfill_met_at.py --ids 12,15,18 --apply --clear-notes

    # Every candidate at once, if you have checked the preview and they all fit.
    uv run python scripts/backfill_met_at.py --all --apply

A row whose met_at is already set is never touched, so re-running is safe.
"""
import argparse
import sys

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit


def fetch_candidates(ids: list[int] | None) -> list[dict]:
    """People carrying notes but no met_at — optionally narrowed to `ids`."""
    query = [
        "SELECT id, name, notes FROM people",
        "WHERE met_at IS NULL AND notes IS NOT NULL AND btrim(notes) <> ''",
    ]
    params: list = []
    if ids:
        query.append("AND id = ANY(%s)")
        params.append(ids)
    query.append("ORDER BY id")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(" ".join(query), params)
        return [dict(row) for row in cur.fetchall()]


def apply_backfill(rows: list[dict], clear_notes: bool) -> int:
    """Copy notes into met_at for `rows`. Returns the number of rows changed."""
    changed = 0
    with db() as conn:
        cur = conn.cursor()
        for row in rows:
            # met_at IS NULL is repeated here so a concurrent edit cannot be
            # overwritten between the preview and the write.
            cur.execute(
                "UPDATE people SET met_at = %s, "
                + ("notes = NULL, " if clear_notes else "")
                + "updated_at = NOW() WHERE id = %s AND met_at IS NULL",
                (row["notes"].strip(), row["id"]),
            )
            if cur.rowcount:
                changed += 1
                log_audit(None, None, "person.met_at_backfilled",
                          f"person:{row['id']}", "updated")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", default="", help="comma-separated person ids to move")
    parser.add_argument("--all", action="store_true", help="every candidate row")
    parser.add_argument("--apply", action="store_true", help="write (default is preview only)")
    parser.add_argument("--clear-notes", action="store_true",
                        help="blank the notes it copied from")
    args = parser.parse_args()

    ids = [int(part) for part in args.ids.split(",") if part.strip()] if args.ids else None
    rows = fetch_candidates(ids)
    if not rows:
        print("No candidates: every person either has met_at set already or has empty notes.")
        return 0

    selected = rows if (ids or args.all) else []
    print(f"{len(rows)} candidate row(s):\n")
    for row in rows:
        mark = "->" if row in selected else "  "
        notes = row["notes"].strip().replace("\n", " ")
        print(f" {mark} [{row['id']:>4}] {(row['name'] or '')[:28]:<28} {notes[:70]}")

    if not selected:
        print("\nNothing selected. Re-run with --ids 1,2,3 (or --all) to choose rows,")
        print("then add --apply to write. Notes are kept unless you pass --clear-notes.")
        return 0
    if not args.apply:
        print(f"\nDRY RUN — would set met_at on {len(selected)} row(s)"
              f"{' and clear their notes' if args.clear_notes else ''}. Add --apply to write.")
        return 0

    changed = apply_backfill(selected, args.clear_notes)
    print(f"\nDone: met_at set on {changed} row(s)"
          f"{'; notes cleared' if args.clear_notes else '; notes left in place'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
