"""
Requeue contacts written off while web search was silently broken.

Background: `duckduckgo-search` stopped returning results and returned an empty
list rather than raising (fixed in 8fe8829 by moving to `ddgs`). Both agents that
depend on it recorded that silence as a fact about the contact:

  * the enrichment agent raises research_exhausted when it finds no
    website, email or phone — and get_contacts_needing_enrichment() excludes that
    status, so the contact is parked permanently rather than merely skipped;
  * the research agent saves a venue with the same status when it finds no web
    presence for it.

Neither verdict is trustworthy for the outage window, so this resets those rows
to 'candidate' and clears enriched_at, putting them back at the front of the
enrichment queue (it orders by `enriched_at ASC NULLS FIRST`).

The cutoff is evidence-based, not a guess: the last enrichment run that enriched
anything started 2026-06-24 16:51, and every run from 17:01 onward reported
0 enriched. Override with --since if that boundary ever needs revisiting.

    uv run python scripts/requeue_failed_enrichment.py            # preview
    uv run python scripts/requeue_failed_enrichment.py --apply    # requeue

Contacts that already have outreach history are never touched — a reply or a
sent email means the row moved on and its status is not the agent's to reset.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.db.connection import db  # noqa: E402
from gcrm.tools.db_audit import log_audit  # noqa: E402

# Parked rows carry the research_exhausted flag; requeueing clears it and puts
# the contact back at the front of the enrichment queue.
DEFAULT_CUTOFF = "2026-06-24 17:00:00+00"

# A contact that was emailed or replied has moved past discovery; whatever its
# status means now, it is not an artefact of a failed lookup.
NO_OUTREACH = (
    "last_emailed_at IS NULL "
    "AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.contact_id = c.id)"
)


def fetch_candidates(cutoff: str) -> dict[str, list[dict]]:
    """The two populations, kept apart because the evidence for each differs."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, name, city, website, email FROM contacts c "
            f"WHERE research_exhausted AND deleted_at IS NULL AND {NO_OUTREACH} "
            f"AND enriched_at >= %s ORDER BY id",
            (cutoff,),
        )
        enrichment = [dict(r) for r in cur.fetchall()]
        cur.execute(
            f"SELECT id, name, city, website, email FROM contacts c "
            f"WHERE research_exhausted AND deleted_at IS NULL AND {NO_OUTREACH} "
            f"AND enriched_at IS NULL AND created_at >= %s ORDER BY id",
            (cutoff,),
        )
        research = [dict(r) for r in cur.fetchall()]
    return {"parked by enrichment": enrichment, "parked by research": research}


def requeue(rows: list[dict]) -> int:
    changed = 0
    with db() as conn:
        cur = conn.cursor()
        for row in rows:
            # Re-check the flag so a row edited since the preview is left alone.
            cur.execute(
                "UPDATE contacts SET research_exhausted = FALSE, enriched_at = NULL, "
                "updated_at = NOW() WHERE id = %s AND research_exhausted",
                (row["id"],),
            )
            if cur.rowcount:
                changed += 1
                log_audit(None, None, "contact.enrichment_requeued",
                          f"contact:{row['id']}", "updated")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=DEFAULT_CUTOFF, help="outage start timestamp")
    parser.add_argument("--apply", action="store_true", help="write (default is preview)")
    args = parser.parse_args()

    groups = fetch_candidates(args.since)
    total = sum(len(rows) for rows in groups.values())
    if not total:
        print("Nothing to requeue.")
        return 0

    print(f"Outage cutoff: {args.since}\n")
    for label, rows in groups.items():
        print(f"{label}: {len(rows)}")
        for row in rows[:5]:
            print(f"    [{row['id']:>4}] {(row['name'] or '')[:38]:<38} {row['city'] or ''}")
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5} more")
        print()

    if not args.apply:
        print(f"DRY RUN — would clear research_exhausted on {total} contact(s) "
              f"and clear enriched_at.")
        print("Add --apply to write.")
        return 0

    changed = sum(requeue(rows) for rows in groups.values())
    print(f"Requeued {changed} contact(s). They re-enter the enrichment queue "
          f"ahead of already-processed rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
