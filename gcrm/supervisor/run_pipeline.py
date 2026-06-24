"""
Run the city-scoped pipeline stages in sequence for one city + level:
research -> scout -> enrichment -> outreach. Stops if a stage fails so a broken
early stage can't feed garbage downstream. (Followup is global — run it
separately.) This backs the 'Run all' button.

Usage:
    uv run python -m gcrm.supervisor.run_pipeline --city Augsburg --level 1
"""
import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run the full city pipeline in sequence")
    parser.add_argument("--city", required=True)
    parser.add_argument("--level", type=int, required=True, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--country", default="DE")
    args = parser.parse_args()

    stages = [
        ("run_research", ["--city", args.city, "--level", str(args.level), "--country", args.country]),
        ("run_scout", ["--city", args.city]),
        ("run_enrichment", ["--city", args.city]),
        ("run_outreach", ["--city", args.city, "--level", str(args.level)]),
    ]
    for module, stage_args in stages:
        logger.info("pipeline: %s for %s (level %s)", module, args.city, args.level)
        result = subprocess.run([sys.executable, "-m", f"gcrm.supervisor.{module}", *stage_args])
        if result.returncode != 0:
            logger.error("pipeline: %s failed (exit %d) — stopping", module, result.returncode)
            sys.exit(result.returncode)
    logger.info("pipeline: complete for %s (level %s)", args.city, args.level)


if __name__ == "__main__":
    main()
