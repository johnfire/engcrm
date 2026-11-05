"""
Judge (plan docs/plans/2026-11-05-gather-judge-reach-plan.md): the scout rates every
candidate, opportunity analysis looks at the ready ones, and the run ends with the list of
companies the scout dropped that are still pinned on the Maps list (for information; the
pins stay). Started by hand only — nothing runs on a schedule.

Usage:
    uv run python -m gcrm.supervisor.run_judge
    uv run python -m gcrm.supervisor.run_judge --limit 50
"""
import argparse
import logging
from collections.abc import Callable

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

NAMES_IN_SUMMARY = 10


def judge(scout: Callable[[], str], analyse: Callable[[], str],
          dropped_on_map: Callable[[], list[dict]]) -> dict:
    """Run each step in turn; one failing never stops the next."""
    outcome = {"summaries": {}, "errors": [], "dropped_on_map": []}
    for name, step in (("scout", scout), ("opportunity", analyse)):
        try:
            outcome["summaries"][name] = step()
        except Exception as error:
            logger.exception("judge: %s failed", name)
            outcome["errors"].append(f"{name} failed: {error}")
    try:
        outcome["dropped_on_map"] = list(dropped_on_map())
    except Exception as error:
        outcome["errors"].append(f"pin check failed: {error}")
    return outcome


def summary_line(outcome: dict) -> str:
    parts = [f"{name}: {summary}" for name, summary in outcome["summaries"].items()]
    dropped = outcome["dropped_on_map"]
    if dropped:
        names = ", ".join(f"{row['name']} #{row['id']}" for row in dropped[:NAMES_IN_SUMMARY])
        more = f" and {len(dropped) - NAMES_IN_SUMMARY} more" if len(dropped) > NAMES_IN_SUMMARY else ""
        parts.append(f"{len(dropped)} dropped but still on your map: {names}{more}")
    return " | ".join(["judge", *parts, *outcome["errors"]])


def main():
    parser = argparse.ArgumentParser(description="Judge: scout, then opportunity analysis of ready companies")
    parser.add_argument("--limit", type=int, default=100, help="Candidates the scout rates this run")
    args = parser.parse_args()

    from gcrm.supervisor.run_opportunity_analysis import analyse
    from gcrm.supervisor.run_scout import scout
    from gcrm.tools import finish_run, start_run
    from gcrm.tools.db_account_lifecycle import get_default_workspace_id
    from gcrm.tools.map_pins import dropped_but_pinned

    run_id = start_run("judge", {"limit": args.limit})
    outcome = judge(lambda: scout(args.limit), lambda: analyse(args.limit),
                    lambda: dropped_but_pinned(get_default_workspace_id()))
    summary = summary_line(outcome)
    finish_run(run_id, "completed" if not outcome["errors"] else "failed", summary[:500],
               {"dropped_on_map": outcome["dropped_on_map"], "errors": outcome["errors"]})
    logger.info(summary)


if __name__ == "__main__":
    main()
