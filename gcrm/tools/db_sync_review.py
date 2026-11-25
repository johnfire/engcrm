"""Read and review offline changes without restoring records implicitly."""

from uuid import uuid4

from psycopg2 import sql

from gcrm.audit_context import current_audit_context
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncCreate, SyncUpdate
from gcrm.sync.validation import validate_sync_patch
from gcrm.tools.db_sync_create import _insert_created, _validate_create
from gcrm.tools.db_sync_push import (
    TABLES,
    _apply_winners,
    _classify_missing,
    _desired_next_step,
    _lock_entity,
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
        cursor.execute("SELECT p.id,p.user_id,p.device_id,p.mutation_id,p.entity_kind,p.entity_sync_id,p.parent_kind,p.parent_sync_id,"
                       "p.reason,p.patch,p.changed_at,p.recorded_at,p.expires_at,p.merge_target_sync_id, "
                       "COALESCE(org.name,person.name,parent_org.name,parent_person.name) AS target_name, survivor.name AS survivor_name "
                       "FROM provisional_mobile_changes p "
                       "LEFT JOIN contacts org ON p.entity_kind='organization' AND org.workspace_id=p.workspace_id AND org.sync_id=p.entity_sync_id "
                       "LEFT JOIN people person ON p.entity_kind='person' AND person.workspace_id=p.workspace_id AND person.sync_id=p.entity_sync_id "
                       "LEFT JOIN contacts parent_org ON p.parent_kind='organization' AND parent_org.workspace_id=p.workspace_id AND parent_org.sync_id=p.parent_sync_id "
                       "LEFT JOIN people parent_person ON p.parent_kind='person' AND parent_person.workspace_id=p.workspace_id AND parent_person.sync_id=p.parent_sync_id "
                       "LEFT JOIN people survivor ON survivor.workspace_id=p.workspace_id AND survivor.sync_id=p.merge_target_sync_id "
                       "WHERE p.workspace_id=%s AND p.status='pending' ORDER BY p.recorded_at,p.id", (workspace_id,))
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


def _restore_parent_and_create(cursor, workspace_id: int, proposal) -> None:
    parent_kind, parent_id = proposal["parent_kind"], proposal["parent_sync_id"]
    cursor.execute(sql.SQL("SELECT * FROM {} WHERE workspace_id=%s AND sync_id=%s FOR UPDATE")
                   .format(sql.Identifier(TABLES[parent_kind])), (workspace_id, parent_id))
    parent = cursor.fetchone()
    if not parent or parent["deleted_at"] is None:
        raise ValueError("The deleted parent is no longer available for restoration")
    creation = SyncCreate(mutation_id=proposal["mutation_id"], device_id=proposal["device_id"],
                          entity_kind=proposal["entity_kind"], entity_sync_id=proposal["entity_sync_id"],
                          operation="create", changed_at=proposal["changed_at"], patch=proposal["patch"])
    if _lock_entity(cursor, workspace_id, creation) or _classify_missing(cursor, workspace_id, creation)[0] != "missing":
        raise ValueError("The offline record can no longer be created")
    cursor.execute(sql.SQL("UPDATE {} SET deleted_at=NULL WHERE workspace_id=%s AND sync_id=%s")
                   .format(sql.Identifier(TABLES[parent_kind])), (workspace_id, parent_id))
    values = _validate_create(cursor, workspace_id, proposal["user_id"], creation)
    _insert_created(cursor, workspace_id, creation, values)


def _restore_existing(cursor, workspace_id: int, proposal) -> None:
    kind = proposal["entity_kind"]
    if kind not in ("person", "organization", "deal"):
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
    winning, _ignored = _split_winning_fields(cursor, workspace_id, proposal["user_id"], mutation, patch)
    if kind == "deal" and any(field in winning for field in ("next_step", "next_step_date")):
        _desired_next_step(entity, patch, winning)
    cursor.execute(sql.SQL("UPDATE {} SET deleted_at=NULL WHERE workspace_id=%s AND sync_id=%s")
                   .format(sql.Identifier(TABLES[kind])), (workspace_id, proposal["entity_sync_id"]))
    _apply_winners(cursor, workspace_id, proposal["user_id"], mutation, patch, winning, entity)


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
        if proposal["reason"] != "soft_deleted":
            raise ValueError("This change cannot restore a record")
        if proposal["parent_kind"] is not None:
            _restore_parent_and_create(cursor, workspace_id, proposal)
        else:
            _restore_existing(cursor, workspace_id, proposal)
        cursor.execute("UPDATE provisional_mobile_changes SET status='applied',reviewed_at=clock_timestamp(),"
                       "reviewed_by=%s,decision='restore' WHERE id=%s AND workspace_id=%s", (reviewer_id, proposal_id, workspace_id))
        cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                       "VALUES (%s,%s,'sync.review_restore',%s,'applied',%s)",
                       (audit.actor, audit.actor_type, f"offline-change:{proposal_id}", audit.correlation_id))
        return True


def _apply_note_to_survivor(cursor, workspace_id: int, proposal, target: str, fields: list[str]) -> None:
    if fields:
        raise ValueError("A note is applied as a whole")
    patch = {**proposal["patch"], "person_sync_id": target}
    creation = SyncCreate(mutation_id=proposal["mutation_id"], device_id=proposal["device_id"], entity_kind="person_note",
                          entity_sync_id=proposal["entity_sync_id"], operation="create", changed_at=proposal["changed_at"], patch=patch)
    if _lock_entity(cursor, workspace_id, creation) or _classify_missing(cursor, workspace_id, creation)[0] != "missing":
        raise ValueError("The offline note can no longer be created")
    values = _validate_create(cursor, workspace_id, proposal["user_id"], creation)
    _insert_created(cursor, workspace_id, creation, values)


def _apply_fields_to_survivor(cursor, workspace_id: int, proposal, target: str, fields: list[str], entity) -> None:
    if not fields or len(fields) != len(set(fields)) or set(fields) - proposal["patch"].keys():
        raise ValueError("Choose fields from the proposed change")
    patch = validate_sync_patch("person", {field: proposal["patch"][field] for field in fields})
    mutation = SyncUpdate(mutation_id=proposal["mutation_id"], device_id=proposal["device_id"], entity_kind="person",
                          entity_sync_id=target, operation="update", changed_at=proposal["changed_at"], patch=patch)
    winning, _ignored = _split_winning_fields(cursor, workspace_id, proposal["user_id"], mutation, patch)
    _apply_winners(cursor, workspace_id, proposal["user_id"], mutation, patch, winning, entity)


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
        person_edit = proposal["entity_kind"] == "person" and proposal["parent_kind"] is None
        person_note = proposal["entity_kind"] == "person_note" and proposal["parent_kind"] == "person"
        if proposal["reason"] != "merged" or not (person_edit or person_note):
            raise ValueError("This change cannot be applied to a merged person")
        reason, target = _resolve_merge_target(cursor, workspace_id, proposal["merge_target_sync_id"])
        if reason != "merged":
            raise ValueError("The surviving person is no longer available")
        cursor.execute("SELECT * FROM people WHERE workspace_id=%s AND sync_id=%s AND deleted_at IS NULL FOR UPDATE", (workspace_id, target))
        entity = cursor.fetchone()
        if not entity:
            raise ValueError("The surviving person is no longer available")
        if person_note:
            _apply_note_to_survivor(cursor, workspace_id, proposal, target, fields)
        else:
            _apply_fields_to_survivor(cursor, workspace_id, proposal, target, fields, entity)
        cursor.execute("UPDATE provisional_mobile_changes SET status='applied',reviewed_at=clock_timestamp(),"
                       "reviewed_by=%s,decision='merge' WHERE id=%s AND workspace_id=%s", (reviewer_id, proposal_id, workspace_id))
        cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                       "VALUES (%s,%s,'sync.review_merge',%s,'applied',%s)",
                       (audit.actor, audit.actor_type, f"offline-change:{proposal_id}", audit.correlation_id))
        return True


def recreate_provisional_change(workspace_id: int, reviewer_id: int, proposal_id: int, name: str) -> str | None:
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
            return None
        kind = proposal["entity_kind"]
        if kind not in ("organization", "person") or proposal["parent_kind"] is not None:
            raise ValueError("Only an organization or person can be recreated")
        if proposal["reason"] == "merged":
            state, _target = _resolve_merge_target(cursor, workspace_id, proposal["merge_target_sync_id"])
            if state != "merged":
                raise ValueError("The surviving person is no longer available")
        else:
            cursor.execute(sql.SQL("SELECT 1 FROM {} WHERE workspace_id=%s AND sync_id=%s AND deleted_at IS NOT NULL FOR UPDATE")
                           .format(sql.Identifier(TABLES[kind])), (workspace_id, proposal["entity_sync_id"]))
            if cursor.fetchone() is None:
                raise ValueError("The deleted record is no longer available")
        patch = validate_sync_patch(kind, {**proposal["patch"], "name": name})
        if not patch.get("name"):
            raise ValueError("A name is required")
        new_id = uuid4()
        creation = SyncCreate(mutation_id=uuid4(), device_id=proposal["device_id"], entity_kind=kind, entity_sync_id=new_id,
                              operation="create", changed_at=proposal["changed_at"], patch=patch)
        _insert_created(cursor, workspace_id, creation, patch)
        cursor.execute("UPDATE provisional_mobile_changes SET status='recreated',reviewed_at=clock_timestamp(),"
                       "reviewed_by=%s,decision='recreate' WHERE workspace_id=%s AND id=%s", (reviewer_id, workspace_id, proposal_id))
        cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                       "VALUES (%s,%s,'sync.review_recreate',%s,%s,%s)",
                       (audit.actor, audit.actor_type, f"offline-change:{proposal_id}", f"created:{new_id}", audit.correlation_id))
        return str(new_id)
