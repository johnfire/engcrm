"""
Record what scripts/maps/pin_loop.js saved on the Maps list. Reads the loop's results (the
JSON window.__pinResults() returns) from stdin. Dry run unless --apply: read the titles of
the dry run first — a saved pin with the wrong title is fixed on the map, not recorded.

    ssh claude@<vps> "docker exec -i engcrm-app python -m scripts.workspace_command scripts/maps/apply_pins.py --apply" < results.json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcrm.audit_context import audit_scope  # noqa: E402
from gcrm.tools.map_pins import PINNED_STATUSES, apply_pin_result  # noqa: E402


def review_lines(results: list[dict]) -> list[str]:
    """One line per result, pins first, so the titles can be checked before recording."""
    ordered = sorted(results, key=lambda r: (r.get("status") not in PINNED_STATUSES, r.get("status") or "", r["id"]))
    return [f"{r.get('status', '?'):14} #{r['id']} {r.get('crm', '')}  →  {r.get('title') or ', '.join(r.get('results') or []) or '—'}"
            for r in ordered]


def main() -> int:
    parser = argparse.ArgumentParser(description="Record pins the browser loop saved (dry run unless --apply)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    results = json.loads(sys.stdin.read())
    print("\n".join(review_lines(results)))
    print("counts:", dict(Counter(r.get("status") for r in results)))
    if not args.apply:
        print("DRY RUN: nothing recorded.")
        return 0
    with audit_scope("claude", "ai"):
        outcomes = Counter(apply_pin_result(r) for r in results)
    print("APPLIED:", dict(outcomes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
