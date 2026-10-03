"""Turn the LinkedIn connections' employers into organizations.

Default is a read-only preview: how many employers would become new
organizations, how many already exist, which need a human. Nothing is written
until you pass --apply. Safe to re-run after every new Connections.csv import:
employers created earlier are found again, never duplicated.

New organizations are created at stage `candidate` with no city (flagged
`needs_review`); every connection at that employer is linked to it.

Usage:
    uv run python -m gcrm.supervisor.run_linkedin_companies            # preview
    uv run python -m gcrm.supervisor.run_linkedin_companies --show 40
    uv run python -m gcrm.supervisor.run_linkedin_companies --apply
    uv run python -m gcrm.supervisor.run_linkedin_companies --apply --limit 50
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--show", type=int, default=15, help="Sample size per category")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default: preview only)")
    parser.add_argument("--limit", type=int, default=None,
                        help="With --apply: create at most this many new organizations")
    args = parser.parse_args()

    from gcrm.tools.db_linkedin import apply_company_plan, get_company_promotion_plan

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

    if args.apply:
        counts = apply_company_plan(plan, limit=args.limit)
        print(f"\napplied: {counts}")
    else:
        print("\npreview only — nothing written. Re-run with --apply to create these.")


if __name__ == "__main__":
    main()
