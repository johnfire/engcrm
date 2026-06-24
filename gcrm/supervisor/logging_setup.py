"""Shared logging configuration for the supervisor run scripts, so the level
and format live in one place instead of being copy-pasted into each script."""
import logging


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
