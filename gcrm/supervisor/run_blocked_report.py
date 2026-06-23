"""
Report contacts that are blocked from outreach and why.

Usage:
    uv run python -m gcrm.supervisor.run_blocked_report
    uv run python -m gcrm.supervisor.run_blocked_report --city "Dießen am Ammersee"
    uv run python -m gcrm.supervisor.run_blocked_report --city ammersee --partial
"""
import argparse

from gcrm.db.connection import db


def main():
    parser = argparse.ArgumentParser(description="Report blocked outreach prospects")
    parser.add_argument("--city", default=None, help="Filter by city name")
    parser.add_argument("--partial", action="store_true", help="Use ILIKE partial match for city")
    args = parser.parse_args()

    with db() as conn:
        cur = conn.cursor()

        city_filter = ""
        params: list = []
        if args.city:
            if args.partial:
                city_filter = "AND lower(c.city) LIKE lower(%s)"
                params.append(f"%{args.city}%")
            else:
                city_filter = "AND lower(c.city) = lower(%s)"
                params.append(args.city)

        cur.execute(f"""
            SELECT
                c.id,
                c.name,
                c.city,
                c.type,
                c.status,
                c.email,
                COALESCE(cl.opt_out, FALSE)            AS opt_out,
                COALESCE(cl.erasure_requested, FALSE)  AS erasure_requested
            FROM contacts c
            LEFT JOIN LATERAL (
                SELECT opt_out, erasure_requested
                FROM consent_log
                WHERE contact_id = c.id
                ORDER BY created_at DESC
                LIMIT 1
            ) cl ON TRUE
            WHERE c.name != '[removed]'
              AND c.deleted_at IS NULL
              {city_filter}
            ORDER BY c.city, c.name
        """, params)
        rows = cur.fetchall()

    blocked = []
    for r in rows:
        reasons = []
        if r["status"] == "do_not_contact":
            reasons.append("do_not_contact status")
        if r["opt_out"]:
            reasons.append("opt-out in consent_log")
        if r["erasure_requested"]:
            reasons.append("erasure requested")
        if not r["email"]:
            reasons.append("no email address")

        if reasons:
            blocked.append({
                "id": r["id"],
                "name": r["name"],
                "city": r["city"],
                "type": r["type"],
                "status": r["status"],
                "reasons": reasons,
            })

    if not blocked:
        print("No blocked contacts found.")
        return

    # Group by city
    by_city: dict[str, list] = {}
    for b in blocked:
        by_city.setdefault(b["city"], []).append(b)

    total = len(blocked)
    print(f"Blocked prospects: {total}\n")

    for city, contacts in sorted(by_city.items()):
        print(f"── {city} ({len(contacts)})")
        for c in contacts:
            reasons_str = ", ".join(c["reasons"])
            print(f"   [{c['id']}] {c['name']} ({c['type']}) — {reasons_str}")
        print()


if __name__ == "__main__":
    main()
