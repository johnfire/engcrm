"""
Gather (plan docs/plans/2026-11-05-gather-judge-reach-plan.md): research an area or a city,
then enrich and find the people at exactly the companies research just saved. Nothing is
judged here; the scout and opportunity analysis are the separate Judge run.

Usage:
    uv run python -m gcrm.supervisor.run_gather --area-id 7 --levels 1,2
    uv run python -m gcrm.supervisor.run_gather --city Untermeitingen --level 2
"""
import argparse
import logging
from collections.abc import Callable

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def gather(research: Callable[[], list[int]], *, enrich: Callable[[list[int]], str],
           find_people: Callable[[list[int]], str]) -> dict:
    """Run research, then each later step on its new ids; one step failing never stops the next."""
    outcome = {"saved_ids": [], "summaries": {}, "errors": []}
    try:
        outcome["saved_ids"] = list(research() or [])
    except Exception as error:
        outcome["errors"].append(f"research failed: {error}")
        return outcome
    if not outcome["saved_ids"]:
        return outcome
    for name, step in (("enrichment", enrich), ("people", find_people)):
        try:
            outcome["summaries"][name] = step(outcome["saved_ids"])
        except Exception as error:
            logger.exception("gather: %s failed", name)
            outcome["errors"].append(f"{name} failed: {error}")
    return outcome


def summary_line(label: str, outcome: dict) -> str:
    parts = [f"gather {label}: {len(outcome['saved_ids'])} new companies"]
    parts += [f"{name}: {summary}" for name, summary in outcome["summaries"].items()]
    parts += outcome["errors"]
    return " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Gather: research, enrichment and people finder for an area or city")
    parser.add_argument("--area-id", type=int, default=None)
    parser.add_argument("--levels", default=None, help="Comma-separated levels for an area, e.g. 1,2")
    parser.add_argument("--city", default=None)
    parser.add_argument("--level", type=int, default=None)
    parser.add_argument("--country", default="DE")
    args = parser.parse_args()

    from gcrm.supervisor.run_enrichment import enrich_ids
    from gcrm.supervisor.run_find_people import run as find_people
    from gcrm.supervisor.run_research import research_area, research_city
    from gcrm.tools import finish_run, start_run

    if args.area_id is not None:
        levels = [int(level) for level in (args.levels or "1").split(",") if level.strip()]
        label, research = f"area #{args.area_id}", lambda: research_area(args.area_id, levels)
    elif args.city and args.level is not None:
        label = f"{args.city} level {args.level}"
        research = lambda: research_city(args.city, args.country, args.level)  # noqa: E731
    else:
        logger.error("Cannot run: give --area-id/--levels or --city/--level")
        return

    run_id = start_run("gather", {"area_id": args.area_id, "city": args.city})
    outcome = gather(research, enrich=enrich_ids,
                     find_people=lambda ids: find_people(limit=len(ids), ids=ids))
    summary = summary_line(label, outcome)
    finish_run(run_id, "failed" if outcome["errors"] and not outcome["saved_ids"] else "completed",
               summary[:500], {"saved_ids": outcome["saved_ids"], "errors": outcome["errors"]})
    logger.info(summary)


if __name__ == "__main__":
    main()
