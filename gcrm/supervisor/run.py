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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"{__import__('pathlib').Path.home()}/logs/supervisor.log",
            mode="a",
        ),
    ],
)

logger = logging.getLogger(__name__)


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
    except Exception as e:
        logger.exception("supervisor: fatal error — %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
