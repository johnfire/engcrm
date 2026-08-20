"""
Requeue contacts the research agent wrote off despite having a website.

Background: fetch_missing_emails() (the research agent's email-discovery step)
only ever fetched a contact's homepage and regex-scanned it for an address.
save_organization()'s own docstring says research_exhausted "records that the
research agent could find no web presence at all" — but the code flagged it
whenever the homepage alone had no visible email, website or not. A contact
with a real, working website (like Fraunhofer IIS — confirmed, notes and all)
was parked exactly the same as one that genuinely doesn't exist online.

Fixed in 50e702d: fetch_missing_emails now also tries /kontakt, /contact,
/impressum and /about before giving up — Impressum is a German legal
disclosure requirement and usually carries a real address the homepage
doesn't.

This resets rows matching the documented contract's violation (flagged
exhausted while a website is on file) and clears enriched_at, putting them
back at the front of the enrichment queue (get_organizations_needing_enrichment
orders by enriched_at ASC NULLS FIRST). The enrichment agent's own
search+LLM pass is a superset of the research agent's regex, so it's the
right place for these to land regardless of which agent originally raised
the flag — this script does not need to know which one did.

    uv run python scripts/requeue_research_exhausted_with_website.py            # preview
    uv run python scripts/requeue_research_exhausted_with_website.py --apply    # requeue

Contacts with outreach history, an opt-out, or a bounced address are never
touched — those facts are not artefacts of a lookup and are not this script's
to reset.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.db.connection import db  # noqa: E402
from gcrm.tools.db_audit import log_audit  # noqa: E402

# A contact that was emailed or replied has moved past discovery; whatever its
# state means now, it is not an artefact of the homepage-only lookup.
NO_OUTREACH = (
    "last_emailed_at IS NULL "
    "AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.contact_id = c.id)"
)

CANDIDATE_QUERY = f"""
    SELECT id, name, city, website, email, enriched_at FROM contacts c
    WHERE research_exhausted
      AND website IS NOT NULL AND website != ''
      AND (email IS NULL OR email = '')
      AND deleted_at IS NULL
      AND NOT do_not_contact
      AND NOT email_bounced
      AND {NO_OUTREACH}
    ORDER BY id
"""


def fetch_candidates() -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(CANDIDATE_QUERY)
        return [dict(r) for r in cur.fetchall()]


def requeue(rows: list[dict]) -> int:
    changed = 0
    with db() as conn:
        cur = conn.cursor()
        for row in rows:
            # Re-check the flag and the website so a row edited since the
            # preview (e.g. by a human clearing it by hand) is left alone.
            cur.execute(
                "UPDATE contacts SET research_exhausted = FALSE, enriched_at = NULL, "
                "updated_at = NOW() WHERE id = %s AND research_exhausted "
                "AND website IS NOT NULL AND website != ''",
                (row["id"],),
            )
            if cur.rowcount:
                changed += 1
                log_audit(None, None, "contact.research_exhausted_requeued",
                          f"contact:{row['id']}", "updated")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write (default is preview)")
    args = parser.parse_args()

    rows = fetch_candidates()
    if not rows:
        print("Nothing to requeue.")
        return 0

    print(f"research_exhausted contacts with a website on file: {len(rows)}\n")
    for row in rows:
        print(f"    [{row['id']:>5}] {(row['name'] or '')[:38]:<38} "
              f"{(row['city'] or '')[:20]:<20} {row['website']}")

    if not args.apply:
        print(f"\nDRY RUN — would clear research_exhausted on {len(rows)} contact(s) "
              f"and clear enriched_at, putting them back at the front of the "
              f"enrichment queue.")
        print("Add --apply to write.")
        return 0

    changed = requeue(rows)
    print(f"\nRequeued {changed} contact(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
