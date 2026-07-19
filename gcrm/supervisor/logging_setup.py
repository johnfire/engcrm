"""Shared logging configuration for the supervisor run scripts, so the level
and format live in one place instead of being copy-pasted into each script."""
import logging

from gcrm.audit_context import CorrelationIdFilter


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s correlation_id=%(correlation_id)s %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(CorrelationIdFilter())
