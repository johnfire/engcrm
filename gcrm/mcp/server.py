"""
general-crm MCP Server

Exposes the supervisor pipeline as MCP tools: approval queue, pipeline status, agent runs,
research triggers, and manual contact management.
"""
import json
import logging
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from gcrm.db.connection import db
from gcrm.tools.db import log_interaction, update_city_market
from gcrm.tools.email import send_email

logger = logging.getLogger(__name__)

server = FastMCP("general-crm", "1.0.0")


# =============================================================================
# PIPELINE STATUS
# =============================================================================

@server.tool()
def pipeline_status() -> str:
    """Get a count of contacts at each pipeline stage: candidate, cold, contacted, dormant, dropped."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT status, COUNT(*) AS count
                FROM contacts
                WHERE name != '[removed]'
                GROUP BY status
                ORDER BY status
            """)
            counts = {row["status"]: row["count"] for row in cur.fetchall()}

            cur.execute("SELECT COUNT(*) AS count FROM approval_queue WHERE status = 'pending'")
            pending_approvals = cur.fetchone()["count"]

        return json.dumps({
            "contacts_by_status": counts,
            "pending_approvals": pending_approvals,
        }, indent=2)
    except Exception as e:
        logger.error("pipeline_status failed: %s", e)
        return json.dumps({"error": str(e)})


# =============================================================================
# DATABASE OVERVIEW
# =============================================================================

@server.tool()
def contacts_list(status: str = "", limit: int = 200) -> str:
    """
    List contacts from the database. Optionally filter by status
    (candidate, cold, contacted, dormant, dropped).
    Returns id, name, city, email, status, fit_score, and last interaction date.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            if status:
                cur.execute("""
                    SELECT c.id, c.name, c.city, c.email, c.type, c.status, c.fit_score, c.notes,
                           MAX(i.interaction_date) AS last_contact
                    FROM contacts c
                    LEFT JOIN interactions i ON i.contact_id = c.id
                    WHERE c.status = %s AND c.name != '[removed]'
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT %s
                """, (status, limit))
            else:
                cur.execute("""
                    SELECT c.id, c.name, c.city, c.email, c.type, c.status, c.fit_score, c.notes,
                           MAX(i.interaction_date) AS last_contact
                    FROM contacts c
                    LEFT JOIN interactions i ON i.contact_id = c.id
                    WHERE c.name != '[removed]'
                    GROUP BY c.id
                    ORDER BY c.status, c.updated_at DESC
                    LIMIT %s
                """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            if r.get("last_contact"):
                r["last_contact"] = str(r["last_contact"])

        return json.dumps(rows, indent=2)
    except Exception as e:
        logger.error("contacts_list failed: %s", e)
        return json.dumps({"error": str(e)})


# =============================================================================
# APPROVAL QUEUE
# =============================================================================

@server.tool()
def approval_list() -> str:
    """List all email drafts currently pending human approval."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    aq.id, aq.draft_subject, aq.draft_body, aq.created_at,
                    c.id AS contact_id, c.name AS contact_name, c.city, c.email
                FROM approval_queue aq
                JOIN contacts c ON c.id = aq.contact_id
                WHERE aq.status = 'pending'
                ORDER BY aq.created_at ASC
            """)
            items = [dict(row) for row in cur.fetchall()]

        for item in items:
            if item.get("created_at"):
                item["created_at"] = str(item["created_at"])

        return json.dumps(items, indent=2)
    except Exception as e:
        logger.error("approval_list failed: %s", e)
        return json.dumps({"error": str(e)})


@server.tool()
def approval_approve(item_id: int, note: str = "") -> str:
    """
    Approve a queued email draft. Sends the email via Proton Bridge SMTP,
    logs the interaction, and moves the contact to status=contacted.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT aq.draft_subject, aq.draft_body, aq.contact_id, c.email, c.name
                FROM approval_queue aq
                JOIN contacts c ON c.id = aq.contact_id
                WHERE aq.id = %s AND aq.status = 'pending'
            """, (item_id,))
            row = cur.fetchone()

        if not row:
            return json.dumps({"error": f"Item {item_id} not found or already reviewed"})

        success = send_email(
            to_email=row["email"] or "",
            subject=row["draft_subject"],
            body=row["draft_body"],
        )
        final_status = "approved" if success else "approved_unsent"

        # Log interaction and mark contacted on approval regardless of send result
        log_interaction(
            contact_id=row["contact_id"],
            method="email",
            direction="outbound",
            summary=row["draft_subject"],
            outcome="no_reply",
        )

        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE approval_queue
                SET status = %s, reviewed_at = NOW(), reviewer_note = %s
                WHERE id = %s
            """, (final_status, note or None, item_id))
            cur.execute("""
                UPDATE contacts SET status = 'contacted', last_emailed_at = NOW(), updated_at = NOW()
                WHERE id = %s AND status IN ('cold', 'on_hold')
            """, (row["contact_id"],))

        return json.dumps({
            "approved": True,
            "sent": success,
            "status": final_status,
            "contact": row["name"],
            "to": row["email"],
        })
    except Exception as e:
        logger.error("approval_approve failed: item_id=%d error=%s", item_id, e)
        return json.dumps({"error": str(e)})


@server.tool()
def approval_reject(item_id: int, note: str = "") -> str:
    """Reject a queued email draft. The contact stays at status=cold for the next run."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE approval_queue
                SET status = 'rejected', reviewed_at = NOW(), reviewer_note = %s
                WHERE id = %s AND status IN ('pending', 'on_hold')
                RETURNING contact_id
            """, (note or None, item_id))
            row = cur.fetchone()
            if not row:
                return json.dumps({"error": f"Item {item_id} not found or already reviewed"})
            cur.execute(
                "UPDATE contacts SET status = 'dropped', updated_at = NOW() WHERE id = %s",
                (row["contact_id"],),
            )

        return json.dumps({"rejected": True, "item_id": item_id})
    except Exception as e:
        logger.error("approval_reject failed: item_id=%d error=%s", item_id, e)
        return json.dumps({"error": str(e)})


# =============================================================================
# AGENT RUNS
# =============================================================================

@server.tool()
def agent_runs(limit: int = 20) -> str:
    """Get recent agent run history — what ran, when, and what happened."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, agent_name, status, summary, started_at, finished_at
                FROM agent_runs
                ORDER BY started_at DESC
                LIMIT %s
            """, (limit,))
            runs = [dict(row) for row in cur.fetchall()]

        for run in runs:
            for key in ("started_at", "finished_at"):
                if run.get(key):
                    run[key] = str(run[key])

        return json.dumps(runs, indent=2)
    except Exception as e:
        logger.error("agent_runs failed: %s", e)
        return json.dumps({"error": str(e)})


# =============================================================================
# MANUAL CONTACT MANAGEMENT
# =============================================================================

@server.tool()
def manual_drop(contact_id: int, reason: str = "") -> str:
    """
    Manually drop a contact — mark as status=dropped with your reason.
    Use this for venues you know are a waste of time, wrong fit, or already visited.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            note = f"[Manually dropped] {reason}".strip() if reason else "[Manually dropped]"
            cur.execute("""
                UPDATE contacts
                SET status = 'dropped',
                    notes = CASE WHEN notes IS NULL OR notes = '' THEN %s
                                 ELSE notes || E'\n' || %s END,
                    updated_at = NOW()
                WHERE id = %s
            """, (note, note, contact_id))
            if cur.rowcount == 0:
                return json.dumps({"error": f"Contact {contact_id} not found"})
            cur.execute("SELECT name, city FROM contacts WHERE id = %s", (contact_id,))
            row = cur.fetchone()
        return json.dumps({"dropped": True, "contact": row["name"], "city": row["city"], "reason": reason})
    except Exception as e:
        return json.dumps({"error": str(e)})


@server.tool()
def manual_promote(contact_id: int, note: str = "") -> str:
    """
    Manually promote a contact to cold — bypasses scout scoring.
    Use this for venues you know personally or are confident are a good fit.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            note_text = f"[Manually promoted] {note}".strip() if note else "[Manually promoted]"
            cur.execute("""
                UPDATE contacts
                SET status = 'cold',
                    notes = CASE WHEN notes IS NULL OR notes = '' THEN %s
                                 ELSE notes || E'\n' || %s END,
                    updated_at = NOW()
                WHERE id = %s
            """, (note_text, note_text, contact_id))
            if cur.rowcount == 0:
                return json.dumps({"error": f"Contact {contact_id} not found"})
            cur.execute("SELECT name, city FROM contacts WHERE id = %s", (contact_id,))
            row = cur.fetchone()
        return json.dumps({"promoted": True, "contact": row["name"], "city": row["city"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@server.tool()
def set_city_notes(city: str, notes: str, character: str = "", country: str = "DE") -> str:
    """
    Add or update market context for a city.
    character: tourist | mixed | upscale | unknown (leave empty to keep existing)
    notes: free text — your observations about the local market.
    This is used by the scout agent when evaluating contacts in this city.
    """
    try:
        found = update_city_market(city, country, character=character, notes=notes)
        if not found:
            return json.dumps({"error": f"City '{city}' not found in registry"})
        return json.dumps({"updated": True, "city": city, "country": country.upper(),
                           "character": character or "unchanged", "notes": notes})
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# RESEARCH STATUS
# =============================================================================

from gcrm.vertical import SCAN_LEVELS
LEVEL_LABELS = {lvl: info["label"] for lvl, info in SCAN_LEVELS.items()}

@server.tool()
def research_status(country: str = "", region: str = "") -> str:
    """
    Show which cities have been scanned and at what levels.
    Optionally filter by country (DE/AT/CH) or region (e.g. Bavaria).
    Returns a readable report grouped by region.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            query = """
                SELECT ci.city, ci.country, ci.region,
                    json_agg(
                        json_build_object('level', cs.level, 'contacts_found', cs.contacts_found,
                                          'last_run_at', cs.last_run_at::text, 'run_count', cs.run_count)
                        ORDER BY cs.level
                    ) FILTER (WHERE cs.level IS NOT NULL) AS scans
                FROM cities ci
                LEFT JOIN city_scans cs ON cs.city_id = ci.id
            """
            conditions = []
            params = []
            if country:
                conditions.append("ci.country = %s")
                params.append(country.upper())
            if region:
                conditions.append("ci.region ILIKE %s")
                params.append(f"%{region}%")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " GROUP BY ci.id, ci.city, ci.country, ci.region ORDER BY ci.country, ci.region, ci.city"
            cur.execute(query, params)
            rows = cur.fetchall()

        # Build readable report
        current_region = None
        lines = []
        total_cities = len(rows)
        scanned = sum(1 for r in rows if r["scans"])
        unscanned = total_cities - scanned

        lines.append(f"Research status: {total_cities} cities | {scanned} scanned | {unscanned} unscanned\n")

        for r in rows:
            reg = f"{r['country']} / {r['region'] or 'Unknown'}"
            if reg != current_region:
                current_region = reg
                lines.append(f"\n{reg}:")
            scans = r["scans"] or []
            if not scans:
                lines.append(f"  {r['city']:30} — not scanned")
            else:
                level_parts = []
                for s in scans:
                    level_parts.append(f"L{s['level']}:{s['contacts_found']}✓")
                unrun = [l for l in range(1, 6) if l not in {s['level'] for s in scans}]
                unrun_str = f"  (L{','.join(map(str,unrun))} pending)" if unrun else ""
                lines.append(f"  {r['city']:30} — {' '.join(level_parts)}{unrun_str}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("research_status failed: %s", e)
        return f"Error: {e}"


@server.tool()
def run_research(city: str, level: int, country: str = "DE") -> str:
    """
    Trigger a research scan for a specific city and level.
    Level 1 must be run before any other level.
    Levels: 1=Galleries/Cafes/Designers, 2=Gift/Esoteric, 3=Restaurants, 4=Corporate, 5=Hotels.
    """
    try:
        project_root = Path(__file__).parent.parent.parent
        uv = Path.home() / ".local" / "bin" / "uv"
        cmd = [
            str(uv), "run", "python", "-m", "gcrm.supervisor.run_research",
            "--city", city, "--level", str(level), "--country", country.upper(),
        ]
        proc = subprocess.Popen(
            cmd, cwd=str(project_root),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        level_label = LEVEL_LABELS.get(level, f"Level {level}")
        return json.dumps({
            "triggered": True,
            "city": city,
            "country": country.upper(),
            "level": level,
            "level_label": level_label,
            "pid": proc.pid,
            "message": f"Research started for {city} level {level} ({level_label}). Check agent_runs for progress.",
        })
    except Exception as e:
        logger.error("run_research failed: %s", e)
        return json.dumps({"error": str(e)})


# =============================================================================
# TRIGGER RUN
# =============================================================================

@server.tool()
def trigger_run() -> str:
    """
    Kick off a full supervisor pipeline run (research → scout → outreach → followup).
    Starts in the background and returns immediately. Check agent_runs for progress.
    Requires the agents extra to be installed: uv sync --extra agents
    """
    try:
        project_root = Path(__file__).parent.parent.parent
        uv = Path.home() / ".local" / "bin" / "uv"
        cmd = [str(uv), "run", "python", "-m", "gcrm.supervisor.run"]

        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return json.dumps({
            "triggered": True,
            "pid": proc.pid,
            "message": "Supervisor run started in background. Check agent_runs for progress.",
        })
    except Exception as e:
        logger.error("trigger_run failed: %s", e)
        return json.dumps({"error": str(e)})


# =============================================================================
# RESOURCES
# =============================================================================

@server.resource("supervisor://pipeline")
def resource_pipeline() -> str:
    """Pipeline overview: contact counts at each stage plus pending approvals."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT status, COUNT(*) AS count
                FROM contacts
                WHERE name != '[removed]'
                GROUP BY status
                ORDER BY status
            """)
            counts = {row["status"]: row["count"] for row in cur.fetchall()}

            cur.execute("SELECT COUNT(*) AS count FROM approval_queue WHERE status = 'pending'")
            pending = cur.fetchone()["count"]

        lines = ["Pipeline status:"]
        for status, count in counts.items():
            lines.append(f"  {status}: {count}")
        lines.append(f"\nPending approvals: {pending}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@server.resource("supervisor://queue")
def resource_queue() -> str:
    """All email drafts pending approval, one per line."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT aq.id, aq.draft_subject, aq.created_at,
                       c.name AS contact_name, c.city, c.email
                FROM approval_queue aq
                JOIN contacts c ON c.id = aq.contact_id
                WHERE aq.status = 'pending'
                ORDER BY aq.created_at ASC
            """)
            items = cur.fetchall()

        if not items:
            return "No pending approvals."

        lines = [f"{len(items)} pending approval(s):\n"]
        for item in items:
            lines.append(
                f"  #{item['id']} | {item['contact_name']} ({item['city']}) "
                f"| {item['draft_subject']} | {str(item['created_at'])[:10]}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# =============================================================================
# PROMPTS
# =============================================================================

@server.prompt()
def review_approvals() -> str:
    """Review the pending approval queue and decide what to approve, edit, or reject."""
    return """Review the pending email approval queue:

1. Use approval_list to see all drafts waiting for review
2. For each draft, read the subject and body carefully
3. Check the contact details — name, city, email
4. Decide:
   - Approve with approval_approve(item_id) if the draft looks good
   - Reject with approval_reject(item_id, note="reason") if it's off
   - Tell me to edit any draft before approving — I'll update it and you approve
5. After reviewing, use pipeline_status to confirm the queue is clear

Notes:
- approval_approve sends the email immediately via Proton Bridge SMTP
- Rejected drafts leave the contact at status=cold — outreach agent will redraft next run
- If Proton Bridge isn't running, the email won't send but will be marked approved_unsent
"""


@server.prompt()
def pipeline_review() -> str:
    """Check the overall health of the pipeline and decide what needs attention."""
    return """Review the state of the outreach pipeline:

1. Use pipeline_status to see how many contacts are at each stage
2. Use agent_runs(limit=10) to see what the agents did recently
3. Use approval_list to check if there are drafts waiting for you
4. Based on what you see, recommend:
   - Whether to trigger a new run (trigger_run)
   - Whether any approvals need immediate attention
   - Whether the pipeline looks healthy or has a bottleneck
"""


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    server.run()
