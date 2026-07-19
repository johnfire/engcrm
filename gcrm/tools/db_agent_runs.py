"""Agent-run logging and per-run cost recording."""
import json

from gcrm.audit_context import set_audit_context
from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit


def start_run(agent_name: str, input_data: dict) -> int:
    """Insert a new agent_run record. Returns run_id. Resets per-run cost counters."""
    from gcrm.tools.costs import reset_costs
    reset_costs()
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO agent_runs (agent_name, status, input_json)
            VALUES (%s, 'running', %s) RETURNING id
            """,
            (agent_name, json.dumps(input_data, default=str)),
        )
        run_id = cur.fetchone()["id"]
    correlation_id = f"run:{run_id}"
    set_audit_context(f"agent:{agent_name}", "ai", correlation_id)
    log_audit(None, None, "agent.run_started", f"agent_run:{run_id}", "running", correlation_id)
    return run_id


def finish_run(run_id: int, status: str, summary: str, output_data: dict) -> None:
    """Update an agent_run record with completion details + record run costs."""
    from gcrm.tools.costs import format_costs, get_costs
    costs = get_costs()
    cost_line = format_costs()
    full_summary = f"{summary} | {cost_line}" if summary else cost_line
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE agent_runs
            SET status = %s, summary = %s, output_json = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (status, full_summary, json.dumps(output_data, default=str), run_id),
        )
        cur.execute(
            """
            INSERT INTO run_costs (run_id, search_queries, llm_usage_json, total_usd)
            VALUES (%s, %s, %s, %s)
            """,
            (
                run_id,
                costs["breakdown"].get("web_search", {}).get("queries", 0),
                json.dumps({key: value for key, value in costs["breakdown"].items() if key != "web_search"}),
                costs["total_usd"],
            ),
        )
        cur.execute("SELECT agent_name FROM agent_runs WHERE id = %s", (run_id,))
        row = cur.fetchone()
    actor = f"agent:{row['agent_name']}" if row else f"agent:run:{run_id}"
    log_audit(actor, "ai", "agent.run_finished", f"agent_run:{run_id}", status, f"run:{run_id}")


def get_run_costs(limit: int = 20) -> list[dict]:
    """Return recent run costs joined with agent_run summaries."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                rc.run_id, ar.agent_name, ar.started_at, ar.finished_at,
                rc.search_queries, rc.llm_usage_json, rc.total_usd
            FROM run_costs rc
            JOIN agent_runs ar ON ar.id = rc.run_id
            ORDER BY rc.recorded_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]
