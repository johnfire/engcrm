"""Run the GDPR erasure and retention job once (schedule daily in production)."""
import logging

from gcrm.tools.privacy_retention import purge_expired_data

logger = logging.getLogger(__name__)


def main() -> None:
    """Run retention once and write only aggregate counts to the application log."""
    logger.info("privacy retention complete: %s", purge_expired_data())


if __name__ == "__main__":
    main()
