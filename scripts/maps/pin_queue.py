"""
Print the companies waiting to be pinned on the Maps list, as items for scripts/maps/pin_loop.js.

    pin_queue.py --import     # the latest lead-list import's companies
    pin_queue.py --gather     # the latest Gather run's companies
    pin_queue.py              # every candidate not pinned yet (id order)

On the server (read-only):
    ssh claude@<vps> "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' engcrm-app \\
        uv run --no-sync python scripts/maps/pin_queue.py --import" > items.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcrm.map_pin_items import loop_item  # noqa: E402
from gcrm.tools.db_account_lifecycle import get_default_workspace_id  # noqa: E402
from gcrm.tools.map_pins import latest_gather_ids, latest_import_ids, pin_queue  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Companies waiting to be pinned, as pin-loop items (JSON)")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--import", dest="from_import", action="store_true", help="Latest lead-list import")
    scope.add_argument("--gather", action="store_true", help="Latest Gather run")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    ids = latest_import_ids() if args.from_import else latest_gather_ids() if args.gather else None
    rows = pin_queue(get_default_workspace_id(), ids=ids, limit=args.limit)
    print(json.dumps([loop_item(row) for row in rows], ensure_ascii=False))


if __name__ == "__main__":
    main()
