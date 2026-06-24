"""
Find emails for approved_unsent contacts and put them back in the approval queue.

Steps:
  1. Run the enrichment agent for each city that has approved_unsent drafts.
  2. For every approved_unsent contact that now has an email, flip the queue
     item back to 'pending' so it reappears in the UI.

Usage:
    uv run python -m gcrm.supervisor.run_requeue_unsent
    uv run python -m gcrm.supervisor.run_requeue_unsent --dry-run
"""
import argparse
import functools
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def get_cities_with_unsent() -> list[str]:
    from gcrm.db.connection import db
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT c.city
            FROM contacts c
            JOIN approval_queue aq ON aq.contact_id = c.id
            WHERE aq.status = 'approved_unsent'
            ORDER BY c.city
        """)
        return [row["city"] for row in cur.fetchall()]


def requeue_contacts_with_email(dry_run: bool = False) -> int:
    from gcrm.db.connection import db
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT aq.id, c.id AS contact_id, c.name, c.city, c.email
            FROM approval_queue aq
            JOIN contacts c ON c.id = aq.contact_id
            WHERE aq.status = 'approved_unsent'
              AND c.email IS NOT NULL AND c.email != ''
        """)
        rows = cur.fetchall()
        if not rows:
            return 0
        for row in rows:
            logger.info("requeue: %s / %s  email=%s  aq_id=%d", row["name"], row["city"], row["email"], row["id"])
        if not dry_run:
            ids = [row["id"] for row in rows]
            cur.execute(
                """
                UPDATE approval_queue
                SET status = 'pending', reviewed_at = NULL, reviewer_note = NULL
                WHERE id = ANY(%s)
                """,
                (ids,),
            )
        return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without changing anything")
    args = parser.parse_args()

    cities = get_cities_with_unsent()
    logger.info("Cities with approved_unsent drafts: %s", cities)

    from gcrm.config import CHEAP_LLM
    from gcrm.tools import (
        get_contacts_needing_enrichment, update_contact_details,
        web_search, fetch_page, start_run, finish_run, get_llm,
    )
    from gcrm_enrichment_agent import create_enrichment_agent

    for city in cities:
        fetch_fn = functools.partial(get_contacts_needing_enrichment, city=city)
        agent = create_enrichment_agent(
            llm=get_llm(CHEAP_LLM),
            web_search=web_search,
            fetch_page=fetch_page,
            fetch_contacts=fetch_fn,
            update_contact=update_contact_details,
            start_run=start_run,
            finish_run=finish_run,
        )
        logger.info("enrichment: running for %s", city)
        result = agent.invoke({"limit": 100})
        logger.info("enrichment %s: %s", city, result.get("summary", ""))

    count = requeue_contacts_with_email(dry_run=args.dry_run)
    if args.dry_run:
        logger.info("dry-run: would requeue %d items", count)
    else:
        logger.info("requeued %d items — they will appear in /approvals/", count)


if __name__ == "__main__":
    main()
