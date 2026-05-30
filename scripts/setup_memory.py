"""
One-time setup for the agent memory system.

Registers topic hints in Open Brain to guide thought classification.

Run once after deploying:
    uv run python scripts/setup_memory.py
"""
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOPIC_HINTS = [
    {
        "topic": "gcrm-outreach",
        "description": "Email tone, word count, subject lines, response rates for engineering CRM outreach",
        "category": "projects",
    },
    {
        "topic": "gcrm-city",
        "description": "City-level notes for gcrm: company density, responsiveness, regional patterns",
        "category": "projects",
    },
    {
        "topic": "gcrm-venue",
        "description": "Company type patterns for gcrm: startups, SMEs, enterprises, consulting firms",
        "category": "projects",
    },
    {
        "topic": "gcrm-seasonal",
        "description": "Seasonal observations for gcrm: hiring cycles, budget cycles, conference seasons",
        "category": "projects",
    },
]


def main():
    from gcrm.tools.memory import _run_tool

    for hint in TOPIC_HINTS:
        result = _run_tool("add_topic_hint", hint)
        logger.info("Registered topic hint '%s': %s", hint["topic"], result[:80] if result else "ok")

    logger.info("Setup complete.")


if __name__ == "__main__":
    main()
