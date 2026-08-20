"""
Run the followup agent standalone — reads inbox and queues overdue nudges.

Usage:
    uv run python -m gcrm.supervisor.run_followup
    uv run python -m gcrm.supervisor.run_followup --overdue-days 60
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run the followup agent standalone")
    parser.add_argument("--overdue-days", type=int, default=90,
                        help="Days without reply before a contact is considered overdue (default: 90)")
    args = parser.parse_args()

    from gcrm_followup_agent import create_followup_agent

    from gcrm.config import ACTIVE_MISSION, SMART_LLM
    from gcrm.tools import (
        finish_run,
        get_llm,
        get_overdue_contacts,
        get_unprocessed_inbox,
        log_interaction,
        mark_bad_email,
        match_organization_by_email,
        queue_for_approval,
        read_inbox,
        record_warm_outcome,
        save_inbox_classification,
        set_opt_out,
        set_visit_when_nearby,
        start_run,
    )

    def fetch_inbox_with_backlog(limit: int = 50) -> list[dict]:
        """Fetch new messages from IMAP, then merge any previously unprocessed DB messages."""
        new_messages = read_inbox(limit=limit)
        new_ids = {message["id"] for message in new_messages}
        backlog = [message for message in get_unprocessed_inbox() if message["id"] not in new_ids]
        if backlog:
            logger.info("fetch_inbox_with_backlog: %d backlog message(s) added", len(backlog))
        return new_messages + backlog

    agent = create_followup_agent(
        llm=get_llm(SMART_LLM),
        fetch_inbox=fetch_inbox_with_backlog,
        match_organization=match_organization_by_email,
        log_interaction=log_interaction,
        set_opt_out=set_opt_out,
        handle_bounce=mark_bad_email,
        set_visit_when_nearby=set_visit_when_nearby,
        save_classification=save_inbox_classification,
        fetch_overdue=get_overdue_contacts,
        queue_for_approval=queue_for_approval,
        record_warm_outcome=record_warm_outcome,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        overdue_days=args.overdue_days,
    )

    logger.info("followup: running (overdue_days=%d)", args.overdue_days)
    result = agent.invoke({})
    logger.info("Done: %s", result.get("summary", ""))


if __name__ == "__main__":
    main()
