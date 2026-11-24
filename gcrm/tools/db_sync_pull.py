"""Read an account-scoped incremental page of canonical sync changes."""

from gcrm.db.connection import db
from gcrm.tools.db_sync_bootstrap import find_sync_entity


def read_sync_changes(workspace_id: int, user_id: int, device_id: str, environment: str,
                      after: int, limit: int) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM mobile_sync_devices WHERE workspace_id=%s AND user_id=%s "
                       "AND device_id=%s AND server_environment=%s AND revoked_at IS NULL",
                       (workspace_id, user_id, device_id, environment))
        if cursor.fetchone() is None:
            return None
        cursor.execute("SELECT pg_advisory_xact_lock(1937337955, %s)", (workspace_id,))
        cursor.execute("SELECT COALESCE((SELECT last_sequence FROM sync_workspace_cursors "
                       "WHERE workspace_id=%s),0) AS high_water", (workspace_id,))
        high_water = cursor.fetchone()["high_water"]
        if after > high_water:
            return {"bootstrap_required": True}
        cursor.execute(
            "SELECT sequence,entity_kind,entity_sync_id,operation,changed_at,merge_target_sync_id "
            "FROM sync_entity_changes WHERE workspace_id=%s AND sequence>%s AND sequence<=%s "
            "AND (target_user_id IS NULL OR target_user_id=%s) ORDER BY sequence LIMIT %s",
            (workspace_id, after, high_water, user_id, limit + 1),
        )
        rows = cursor.fetchall()
        has_more = len(rows) > limit
        visible = rows[:limit]
        changes = [_resolve_change(cursor, workspace_id, user_id, row) for row in visible]
        next_cursor = visible[-1]["sequence"] if has_more else high_water
        return {"changes": changes, "next_cursor": next_cursor, "has_more": has_more}


def _resolve_change(cursor, workspace_id: int, user_id: int, row) -> dict:
    kind, sync_id = row["entity_kind"], row["entity_sync_id"]
    entity = find_sync_entity(cursor, workspace_id, user_id, kind, sync_id)
    if entity is not None:
        return {"sequence": row["sequence"], "operation": "upsert", **entity}
    cursor.execute("SELECT operation,changed_at,merge_target_sync_id FROM sync_entity_changes "
                   "WHERE workspace_id=%s AND entity_kind=%s AND entity_sync_id=%s "
                   "AND (target_user_id IS NULL OR target_user_id=%s) "
                   "ORDER BY sequence DESC LIMIT 1", (workspace_id, kind, sync_id, user_id))
    latest = cursor.fetchone()
    operation = latest["operation"] if latest and latest["operation"] != "upsert" else "soft_delete"
    tombstone = {"sequence": row["sequence"], "entity_kind": kind, "sync_id": sync_id,
                 "operation": operation, "changed_at": latest["changed_at"] if latest else row["changed_at"]}
    if operation == "merge_redirect":
        tombstone["merge_target_sync_id"] = latest["merge_target_sync_id"]
    return tombstone
