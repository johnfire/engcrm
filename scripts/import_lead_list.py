"""
Import a lead list (the Markdown master table of HOWTO-city-lead-lists.md) into the CRM.
Plain parsing and matching, no LLM. Dry run unless --apply.

    uv run python scripts/import_lead_list.py ~/ai-workzone/marketing-leads/buchloe-office-parks.md --town Buchloe
    uv run python scripts/import_lead_list.py <file> --town Buchloe --apply

On the server the file is read from stdin:
    ssh claude@<vps> "docker exec -i engcrm-app python -m scripts.workspace_command scripts/import_lead_list.py - \\
        --list-name buchloe-office-parks --town Buchloe" < buchloe-office-parks.md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.audit_context import audit_scope  # noqa: E402
from gcrm.lead_list import LeadListError, parse_lead_list  # noqa: E402
from gcrm.tools.db_lead_import import import_lead_list, summary_line  # noqa: E402


def parse_same(pairs: list[str]) -> dict[str, int]:
    """'ICO Institut f. Coaching & Organisation GbR=1206' -> {name: 1206}. The id is after the
    last '=', so a name may itself contain '='."""
    same = {}
    for pair in pairs:
        name, _, crm_id = pair.rpartition("=")
        if not name.strip() or not crm_id.strip().isdigit():
            raise ValueError(f"--same needs 'LIST NAME=CRM ID', got {pair!r}")
        same[name.strip()] = int(crm_id)
    return same


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a lead list into the CRM (dry run unless --apply)")
    parser.add_argument("file", help="Markdown lead list, or - for stdin")
    parser.add_argument("--town", default="", help="Town for rows whose address names none")
    parser.add_argument("--list-name", default="", help="Name recorded on each company (default: file name)")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: dry run)")
    parser.add_argument("--actor", default="claude", help="Who runs the import, for the audit log")
    parser.add_argument("--similar", choices=("match", "new"),
                        help="Possible duplicates: 'match' takes them as the existing companies, 'new' creates them")
    parser.add_argument("--same", action="append", default=[], metavar="'LIST NAME=CRM ID'",
                        help="Take this list business as that CRM company (repeatable), for duplicates "
                             "the name check does not see")
    args = parser.parse_args()
    try:
        same = parse_same(args.same)
    except ValueError as error:
        print(f"Not imported: {error}")
        return 1

    text = sys.stdin.read() if args.file == "-" else Path(args.file).expanduser().read_text(encoding="utf-8")
    list_name = args.list_name or (Path(args.file).stem if args.file != "-" else "lead list")
    try:
        businesses = parse_lead_list(text)
    except LeadListError as error:
        print(f"Not imported: {error}")
        return 1
    try:
        with audit_scope(args.actor, "ai" if args.actor == "claude" else "user"):
            report = import_lead_list(businesses, list_name=list_name, default_town=args.town,
                                      apply=args.apply, similar=args.similar, same=same)
    except ValueError as error:
        print(f"Not imported: {error}")
        return 1
    print(("APPLIED: " if args.apply else "DRY RUN (nothing written): ") + summary_line(report, list_name))
    for entry in report["possible_duplicates"]:
        print(f"  possible duplicate: {entry['name']}  ~  CRM #{entry['crm_id']} {entry['crm_name']}")
    for name in report["skipped_no_town"]:
        print(f"  skipped, no town (pass --town): {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
