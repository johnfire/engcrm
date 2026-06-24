"""
Audit the Proton Mail Sent folder against the database.

Finds contacts whose email was sent to but are not marked as 'contacted'
(or a further-along status), then offers to fix them.

Usage:
    uv run python -m gcrm.supervisor.run_email_audit
    uv run python -m gcrm.supervisor.run_email_audit --city Lindau
    uv run python -m gcrm.supervisor.run_email_audit --fix        # auto-apply fixes
    uv run python -m gcrm.supervisor.run_email_audit --city Lindau --fix
"""
import argparse
import imaplib
import logging
import re
from datetime import date

from gcrm.config import (
    PROTON_IMAP_HOST, PROTON_IMAP_PORT, PROTON_EMAIL, PROTON_PASSWORD,
)

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# Statuses that mean "we already have contact" — don't downgrade these
ACTIVE_STATUSES = {"contacted", "networking_visit", "meeting", "accepted", "on_hold", "closed"}
# Statuses that should be upgraded to 'contacted' if email was found in Sent
UPGRADEABLE_STATUSES = {"cold", "candidate", "dormant", "lead_unverified", "maybe"}


def fetch_sent_recipients(imap_host: str, imap_port: int, username: str, password: str) -> set[str]:
    """Return all unique recipient email addresses from the Sent folder."""
    logger.info("Connecting to IMAP at %s:%d", imap_host, imap_port)
    m = imaplib.IMAP4(imap_host, imap_port)
    m.login(username, password)
    m.select("Sent", readonly=True)

    _, data = m.search(None, "ALL")
    msg_ids = data[0].split()
    logger.info("Found %d messages in Sent folder", len(msg_ids))

    recipients = set()
    for chunk_start in range(0, len(msg_ids), 100):
        chunk = msg_ids[chunk_start:chunk_start + 100]
        id_str = ",".join(i.decode() for i in chunk)
        _, fetch_data = m.fetch(id_str, "(BODY.PEEK[HEADER.FIELDS (TO CC)])")
        for item in fetch_data:
            if not isinstance(item, tuple):
                continue
            raw = item[1].decode(errors="replace")
            # Extract all email addresses from To/CC headers
            for addr in re.findall(r"[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}", raw):
                recipients.add(addr.lower())

    m.logout()
    logger.info("Extracted %d unique recipient addresses", len(recipients))
    return recipients


def get_contacts(city: str | None) -> list[dict]:
    from gcrm.db.connection import db
    with db() as conn:
        cur = conn.cursor()
        if city:
            cur.execute(
                "SELECT id, name, city, email, status FROM contacts WHERE lower(city) = lower(%s) AND email IS NOT NULL AND email != '' AND deleted_at IS NULL",
                (city,),
            )
        else:
            cur.execute(
                "SELECT id, name, city, email, status FROM contacts WHERE email IS NOT NULL AND email != '' AND deleted_at IS NULL"
            )
        return [dict(r) for r in cur.fetchall()]


def mark_contacted(contact_ids: list[int]) -> None:
    from gcrm.db.connection import db
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET status = 'contacted', updated_at = NOW() WHERE id = ANY(%s)",
            (contact_ids,),
        )
        # Log an interaction for each
        for cid in contact_ids:
            cur.execute(
                """
                INSERT INTO interactions (contact_id, interaction_date, method, direction, outcome, summary)
                VALUES (%s, %s, 'email', 'outbound', 'no_reply', 'Marked contacted via Sent folder audit')
                """,
                (cid, date.today()),
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default=None, help="Limit to one city")
    parser.add_argument("--fix", action="store_true", help="Apply fixes automatically")
    args = parser.parse_args()

    sent_recipients = fetch_sent_recipients(
        imap_host=PROTON_IMAP_HOST,
        imap_port=PROTON_IMAP_PORT,
        username=PROTON_EMAIL,
        password=PROTON_PASSWORD,
    )

    contacts = get_contacts(args.city)
    label = args.city or "all cities"
    logger.info("Checking %d contacts with emails in %s", len(contacts), label)

    to_fix = []
    already_ok = []
    not_found = []

    for c in contacts:
        addr = c["email"].lower().strip()
        if addr in sent_recipients:
            if c["status"] in ACTIVE_STATUSES:
                already_ok.append(c)
            elif c["status"] in UPGRADEABLE_STATUSES:
                to_fix.append(c)
            # dropped / do_not_contact — leave alone
        else:
            not_found.append(c)

    print(f"\n── Sent Folder Audit — {label} ──────────────────────")
    print(f"  Sent folder recipients : {len(sent_recipients)}")
    print(f"  Contacts checked       : {len(contacts)}")
    print(f"  Already correctly marked : {len(already_ok)}")
    print(f"  Need fixing (emailed but wrong status) : {len(to_fix)}")
    print(f"  No sent email found    : {len(not_found)}")

    if to_fix:
        print(f"\n── Contacts to fix ({'will auto-apply' if args.fix else 'dry run — use --fix to apply'}) ──")
        for c in to_fix:
            print(f"  [{c['status']:20s}] → contacted   {c['name']} ({c['city']})  <{c['email']}>")

        if args.fix:
            ids = [c["id"] for c in to_fix]
            mark_contacted(ids)
            print(f"\n  Fixed {len(ids)} contact(s).")
        else:
            print(f"\n  Run with --fix to apply these {len(to_fix)} change(s).")
    else:
        print("\n  Nothing to fix.")


if __name__ == "__main__":
    main()
