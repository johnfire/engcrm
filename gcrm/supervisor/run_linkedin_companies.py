"""Preview which organizations the LinkedIn connections' employers would create.

Read-only: writes nothing. Prints how many employers would become new
organizations, how many already exist, and which need a human.

Usage:
    uv run python -m gcrm.supervisor.run_linkedin_companies
    uv run python -m gcrm.supervisor.run_linkedin_companies --show 40
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--show", type=int, default=15, help="Sample size per category")
    args = parser.parse_args()

    from gcrm.tools.db_linkedin import get_company_promotion_plan

    plan = get_company_promotion_plan()
    people_in = lambda groups: sum(len(g["people_ids"]) for g in groups)  # noqa: E731
    print(f"would create : {len(plan.create):5d} organizations ({people_in(plan.create)} people)")
    print(f"link existing: {len(plan.link):5d} organizations ({people_in(plan.link)} people)")
    print(f"ambiguous    : {len(plan.ambiguous):5d} (same name as several organizations)")
    print(f"no company   : {plan.skipped_no_company:5d} people skipped (blank / self-employed)")

    for title, groups in (("CREATE", plan.create), ("LINK", plan.link), ("AMBIGUOUS", plan.ambiguous)):
        if not groups:
            continue
        print(f"\n{title} (largest first)")
        for group in sorted(groups, key=lambda g: -len(g["people_ids"]))[: args.show]:
            extra = ""
            if group.get("near"):
                extra = "  ~ near: " + ", ".join(n["name"] for n in group["near"])
            if group.get("contact_name"):
                extra = f"  -> {group['contact_name']}"
            print(f"  {len(group['people_ids']):3d}  {group['name']}{extra}")


if __name__ == "__main__":
    main()
