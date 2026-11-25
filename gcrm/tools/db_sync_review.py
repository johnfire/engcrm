"""Read and review offline changes without restoring records implicitly."""

from psycopg2 import sql

from gcrm.audit_context import current_audit_context
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncUpdate
from gcrm.sync.validation import validate_sync_patch
from gcrm.tools.db_sync_push import (
    TABLES,
    _apply_winners,
    _desired_next_step,
    _resolve_merge_target,
    _split_winning_fields,
)


def _require_workspace_admin(cursor, workspace_id: int, reviewer_id: int) -> None:
    cursor.execute("SELECT 1 FROM users WHERE id=%s AND workspace_id=%s AND role='admin' AND is_active FOR SHARE", (reviewer_id, workspace_id))
    if cursor.fetchone() is None:
        raise PermissionError("An active workspace administrator is required")


def list_provisional_changes(workspace_id: int, reviewer_id: int) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        _require_workspace_admin(cursor, workspace_id, reviewer_id)
        cursor.execute("SELECT id,user_id,device_id,mutation_id,entity_kind,entity_sync_id,parent_kind,parent_sync_id,"
                       "reason,patch,changed_at,recorded_at,expires_at,merge_target_sync_id "
                       "FROM provisional_mobile_changes WHERE workspace_id=%s AND status='pending' "
                       "ORDER BY recorded_at,id", (workspace_id,))
        return [dict(row) for row in cursor.fetchall()]


def read_review_outcomes(workspace_id: int, user_id: int, device_id: str, environment: str,
                         mutation_ids: list[str]) -> list[dict]:
    if not 1 <= len(mutation_ids) <= 100:
        raise ValueError("Request between one and 100 review outcomes")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM mobile_sync_devices WHERE workspace_id=%s AND user_id=%s AND device_id=%s "
                       "AND server_environment=%s AND revoked_at IS NULL FOR SHARE", (workspace_id, user_id, device_id, environment))
        if cursor.fetchone() is None:
            raise PermissionError("Sync device is unregistered or revoked")
        cursor.execute("SELECT m.mutation_id,CASE WHEN m.status='erased' THEN 'erased' ELSE p.status END AS status "
                       "FROM sync_mutations m LEFT JOIN provisional_mobile_changes p ON "
                       "(p.workspace_id,p.device_id,p.mutation_id)=(m.workspace_id,m.device_id,m.mutation_id) "
                       "WHERE m.workspace_id=%s AND m.user_id=%s AND m.device_id=%s AND m.mutation_id=ANY(%s::uuid[]) "
                       "AND (m.status='erased' OR (m.status='provisional' AND p.status IS NOT NULL)) ORDER BY m.mutation_id",
                       (workspace_id, user_id, device_id, mutation_ids))
        return [{"mutation_id": str(row["mutation_id"]), "status": row["status"]} for row in cursor.fetchall()]


def discard_provisional_change(workspace_id: int, reviewer_id: int, proposal_id: int) -> bool:
    audit = current_audit_context()
    if audit is None:
        raise RuntimeError("Offline review requires an audit identity")
    with db() as connection:
        cursor = connection.cursor()
        _require_workspace_admin(cursor, workspace_id, reviewer_id)
        cursor.execute("UPDATE provisional_mobile_changes SET status='discarded',patch=NULL,reviewed_at=clock_timestamp(),"
                       "reviewed_by=%s,decision='discard' WHERE workspace_id=%s AND id=%s AND status='pending' RETURNING id",
                       (reviewer_id, workspace_id, proposal_id))
        if cursor.fetchone() is None:
            return False
        cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                       "VALUES (%s,%s,'sync.review_discard',%s,'discarded',%s)",
                       (audit.actor, audit.actor_type, f"offline-change:{proposal_id}", audit.correlation_id))
        return True


def restore_provisional_change(workspace_id: int, reviewer_id: int, proposal_id: int) -> bool:
    audit = current_audit_context()
    if audit is None:
        raise RuntimeError("Offline review requires an audit identity")
    with db() as connection:
        cursor = connection.cursor()
        _require_workspace_admin(cursor, workspace_id, reviewer_id)
        cursor.execute("SELECT * FROM provisional_mobile_changes WHERE workspace_id=%s AND id=%s AND status='pending' FOR UPDATE",
                       (workspace_id, proposal_id))
        proposal = cursor.fetchone()
        if not proposal:
            return False
        kind = proposal["entity_kind"]
        if proposal["reason"] != "soft_deleted" or proposal["parent_kind"] is not None or kind not in ("person", "organization", "deal"):
            raise ValueError("This change cannot restore a record")
        patch = validate_sync_patch(kind, proposal["patch"])
        mutation = SyncUpdate(mutation_id=proposal["mutation_id"], device_id=proposal["device_id"],
                              entity_kind=kind, entity_sync_id=proposal["entity_sync_id"],
                              operation="update", changed_at=proposal["changed_at"], patch=patch)
        cursor.execute(sql.SQL("SELECT * FROM {} WHERE workspace_id=%s AND sync_id=%s FOR UPDATE")
                       .format(sql.Identifier(TABLES[kind])), (workspace_id, proposal["entity_sync_id"]))
        entity = cursor.fetchone()
        if not entity or entity["deleted_at"] is None:
            raise ValueError("The deleted record is no longer available for restoration")
        winning, _ignored = _split_winning_fields(cursor, workspace_id, mutation, patch)
        if kind == "deal" and any(field in winning for field in ("next_step", "next_step_date")):
            _desired_next_step(entity, patch, winning)
        cursor.execute(sql.SQL("UPDATE {} SET deleted_at=NULL WHERE workspace_id=%s AND sync_id=%s")
                       .format(sql.Identifier(TABLES[kind])), (workspace_id, proposal["entity_sync_id"]))
        _apply_winners(cursor, workspace_id, mutation, patch, winning, entity)
        cursor.execute("UPDATE provisional_mobile_changes SET status='applied',reviewed_at=clock_timestamp(),"
                       "reviewed_by=%s,decision='restore' WHERE id=%s AND workspace_id=%s", (reviewer_id, proposal_id, workspace_id))
        cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                       "VALUES (%s,%s,'sync.review_restore',%s,'applied',%s)",
                       (audit.actor, audit.actor_type, f"offline-change:{proposal_id}", audit.correlation_id))
        return True


def apply_merged_provisional_change(workspace_id: int, reviewer_id: int, proposal_id: int, fields: list[str]) -> bool:
    audit = current_audit_context()
    if audit is None:
        raise RuntimeError("Offline review requires an audit identity")
    with db() as connection:
        cursor = connection.cursor()
        _require_workspace_admin(cursor, workspace_id, reviewer_id)
        cursor.execute("SELECT * FROM provisional_mobile_changes WHERE workspace_id=%s AND id=%s AND status='pending' FOR UPDATE",
                       (workspace_id, proposal_id))
        proposal = cursor.fetchone()
        if not proposal:
            return False
        if proposal["reason"] != "merged" or proposal["entity_kind"] != "person" or proposal["parent_kind"] is not None:
            raise ValueError("This change cannot be applied to a merged person")
        if not fields or len(fields) != len(set(fields)) or set(fields) - proposal["patch"].keys():
            raise ValueError("Choose fields from the proposed change")
        patch = validate_sync_patch("person", {field: proposal["patch"][field] for field in fields})
        reason, target = _resolve_merge_target(cursor, workspace_id, proposal["merge_target_sync_id"])
        if reason != "merged":
            raise ValueError("The surviving person is no longer available")
        cursor.execute("SELECT * FROM people WHERE workspace_id=%s AND sync_id=%s AND deleted_at IS NULL FOR UPDATE", (workspace_id, target))
        entity = cursor.fetchone()
        if not entity:
            raise ValueError("The surviving person is no longer available")
        mutation = SyncUpdate(mutation_id=proposal["mutation_id"], device_id=proposal["device_id"], entity_kind="person",
                              entity_sync_id=target, operation="update", changed_at=proposal["changed_at"], patch=patch)
        winning, _ignored = _split_winning_fields(cursor, workspace_id, mutation, patch)
        _apply_winners(cursor, workspace_id, mutation, patch, winning, entity)
        cursor.execute("UPDATE provisional_mobile_changes SET status='applied',reviewed_at=clock_timestamp(),"
                       "reviewed_by=%s,decision='merge' WHERE id=%s AND workspace_id=%s", (reviewer_id, proposal_id, workspace_id))
        cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                       "VALUES (%s,%s,'sync.review_merge',%s,'applied',%s)",
                       (audit.actor, audit.actor_type, f"offline-change:{proposal_id}", audit.correlation_id))
        return True
