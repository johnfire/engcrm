"""Compare and apply per-account mobile rating clocks."""

from uuid import UUID

from gcrm.audit_context import current_audit_context
from gcrm.sync.conflict_resolution import FieldVersion, is_incoming_version_newer
from gcrm.sync.validation import PRIVATE_FIELDS
from gcrm.tools.db_personal_ratings import store_rating


def private_winners(cursor, workspace_id: int, user_id: int, update, fields: list[str]) -> tuple[list[str], list[str]]:
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                   (f"sync-private:{workspace_id}:{user_id}:{update.entity_kind}:{update.entity_sync_id}",))
    cursor.execute("SELECT field_name,changed_at,device_id,mutation_id FROM sync_private_field_versions "
                   "WHERE workspace_id=%s AND user_id=%s AND entity_kind=%s AND entity_sync_id=%s AND field_name=ANY(%s)",
                   (workspace_id, user_id, update.entity_kind, str(update.entity_sync_id), fields))
    versions = {row["field_name"]: FieldVersion(row["changed_at"], UUID(str(row["device_id"])), UUID(str(row["mutation_id"])))
                for row in cursor.fetchall()}
    incoming = FieldVersion(update.changed_at, update.device_id, update.mutation_id)
    winning = [field for field in fields if field not in versions or is_incoming_version_newer(incoming, versions[field])]
    return winning, [field for field in fields if field not in winning]


def _rating_location(kind: str) -> tuple[str, str]:
    return ("person_user_priorities", "person_id") if kind == "person" else ("contact_user_priorities", "contact_id")


def _write_private_clock(cursor, workspace_id: int, user_id: int, update, field: str) -> None:
    cursor.execute("INSERT INTO sync_private_field_versions(workspace_id,user_id,entity_kind,entity_sync_id,field_name,"
                   "changed_at,device_id,mutation_id,source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'mobile') "
                   "ON CONFLICT (workspace_id,user_id,entity_kind,entity_sync_id,field_name) DO UPDATE SET "
                   "changed_at=EXCLUDED.changed_at,device_id=EXCLUDED.device_id,mutation_id=EXCLUDED.mutation_id,source='mobile'",
                   (workspace_id, user_id, update.entity_kind, str(update.entity_sync_id), field, update.changed_at,
                    str(update.device_id), str(update.mutation_id)))


def apply_private_winners(cursor, workspace_id: int, user_id: int, update, patch: dict, winning: list[str], entity) -> None:
    private = [field for field in winning if field in PRIVATE_FIELDS.get(update.entity_kind, set())]
    if not private:
        return
    table, owner_column = _rating_location(update.entity_kind)
    cursor.execute(f"SELECT priority,short_term_value,long_term_value FROM {table} WHERE workspace_id=%s AND user_id=%s "
                   f"AND {owner_column}=%s FOR UPDATE", (workspace_id, user_id, entity["id"]))
    current = cursor.fetchone() or {}
    had_noop = False
    for field in private:
        rating = "priority" if field in ("personal_priority", "value_rating") else field
        if current.get(rating) == patch[field]:
            had_noop = True
        else:
            store_rating(cursor, table, user_id, workspace_id, entity["id"], rating, patch[field])
        _write_private_clock(cursor, workspace_id, user_id, update, field)
    if had_noop:
        audit = current_audit_context()
        cursor.execute("INSERT INTO sync_entity_changes(workspace_id,entity_kind,entity_sync_id,operation,changed_at,"
                       "device_id,mutation_id,actor,correlation_id,target_user_id) VALUES (%s,%s,%s,'upsert',%s,%s,%s,%s,%s,%s)",
                       (workspace_id, update.entity_kind, str(update.entity_sync_id), update.changed_at,
                        str(update.device_id), str(update.mutation_id), audit.actor, audit.correlation_id, user_id))
