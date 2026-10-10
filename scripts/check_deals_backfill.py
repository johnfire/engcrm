"""
Check migration 064 on a live database: every organization's and person's old
stage (now the legacy_* columns) must have become the same Consulting deal.
Read-only. Run it right after the deploy — from then on the deals move and the
frozen legacy columns fall behind, so later differences are expected.

Usage (on the VPS, in /opt/engcrm):
    sudo docker compose run --rm app uv run python scripts/check_deals_backfill.py

Exit code 0 when everything matches, 1 when anything does not.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from gcrm.db.connection import db  # noqa: E402
from gcrm.tools.db_deals import organization_deal_join, person_deal_join  # noqa: E402

ORGANIZATIONS = (
    "SELECT c.id, c.name, COALESCE(NULLIF(c.legacy_pipeline_stage, ''), 'candidate') AS was_stage, "
    "COALESCE(NULLIF(c.legacy_status, ''), 'none') AS was_status, d.pipeline_stage, d.status "
    "FROM contacts c" + organization_deal_join("c", "d")
    + "WHERE d.id IS NULL OR d.pipeline_stage IS DISTINCT FROM COALESCE(NULLIF(c.legacy_pipeline_stage, ''), "
    "'candidate') OR d.status IS DISTINCT FROM COALESCE(NULLIF(c.legacy_status, ''), 'none') ORDER BY c.id"
)
PEOPLE = (
    "SELECT p.id, p.name, NULLIF(p.legacy_pipeline_stage, '') AS was_stage, "
    "NULLIF(btrim(p.legacy_next_step), '') AS was_next_step, p.legacy_next_step_date AS was_next_step_date, "
    "d.pipeline_stage, d.next_step, d.next_step_date FROM people p" + person_deal_join("p", "d")
)
COUNTS = (
    "SELECT 'organization' AS owner, d.pipeline_stage AS stage, COUNT(*) AS n FROM contacts c"
    + organization_deal_join("c", "d") + "WHERE c.deleted_at IS NULL AND d.id IS NOT NULL GROUP BY 2 UNION ALL "
    "SELECT 'person', d.pipeline_stage, COUNT(*) FROM people p" + person_deal_join("p", "d")
    + "WHERE p.deleted_at IS NULL AND d.id IS NOT NULL GROUP BY 2 ORDER BY 1, 2"
)


def _person_problem(row: dict) -> str | None:
    had_something = row["was_stage"] or row["was_next_step"] or row["was_next_step_date"]
    if not had_something:
        return "has a deal but had no stage and no next step" if row["pipeline_stage"] else None
    if row["pipeline_stage"] is None:
        return "had a stage or next step but has no deal"
    expected_stage = row["was_stage"] or "candidate"
    if row["pipeline_stage"] != expected_stage:
        return f"stage {row['was_stage']!r} became {row['pipeline_stage']!r}"
    if (row["was_next_step"], row["was_next_step_date"]) != (row["next_step"], row["next_step_date"]):
        return f"next step {row['was_next_step']!r} became {row['next_step']!r}"
    return None


def main() -> int:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(ORGANIZATIONS)
        organizations = cur.fetchall()
        cur.execute(PEOPLE)
        people = cur.fetchall()
        cur.execute(COUNTS)
        counts = cur.fetchall()

    print("Consulting deals per stage (live records):")
    for row in counts:
        print(f"  {row['owner']:<13} {row['stage']:<16} {row['n']:>6}")

    for row in organizations:
        print(f"MISMATCH organization {row['id']} {row['name']!r}: was {row['was_stage']}/{row['was_status']}, "
              f"deal {row['pipeline_stage']}/{row['status']}")
    person_problems = [(row, problem) for row in people if (problem := _person_problem(row))]
    for row, problem in person_problems:
        print(f"MISMATCH person {row['id']} {row['name']!r}: {problem}")

    promoted = [row for row in people if not row["was_stage"] and row["pipeline_stage"] == "candidate"]
    if promoted:
        print(f"\n{len(promoted)} people had a next step but no stage; they are now Consulting candidates:")
        for row in promoted:
            print(f"  person {row['id']} {row['name']!r}: {row['next_step']!r}")

    problems = len(organizations) + len(person_problems)
    print(f"\n{'OK' if not problems else 'FAILED'}: {len(people)} people and every organization checked, "
          f"{problems} mismatch(es).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
