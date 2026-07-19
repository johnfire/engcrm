"""
Entry point to trigger a supervisor run.

Usage:
    uv run python -m gcrm.supervisor.run

Each run gets a unique thread_id (date + hour) so that:
- Runs on the same day/hour resume from a checkpoint if they crash
- A new hour always starts fresh
- You can trigger multiple runs per day by waiting until the next hour
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from gcrm.audit_context import CorrelationIdFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"{Path.home()}/logs/supervisor.log",
            mode="a",
        ),
    ],
)

logger = logging.getLogger(__name__)
for handler in logging.getLogger().handlers:
    handler.addFilter(CorrelationIdFilter())


def main():
    from langgraph.checkpoint.postgres import PostgresSaver

    from gcrm.config import DATABASE_URL
    from gcrm.supervisor.graph import create_supervisor

    thread_id = f"supervisor-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H')}"
    logger.info("supervisor: thread_id=%s", thread_id)

    try:
        with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
            checkpointer.setup()
            supervisor = create_supervisor(checkpointer=checkpointer)
            result = supervisor.invoke(
                {},
                config={"configurable": {"thread_id": thread_id}},
            )
            print(result["summary"])
    except Exception as error:
        logger.exception("supervisor: fatal error — %s", error)
        sys.exit(1)


if __name__ == "__main__":
    main()
