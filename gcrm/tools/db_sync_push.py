"""Apply one idempotent, field-clocked offline update in a single transaction."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from psycopg2 import sql
from psycopg2.extras import Json

from gcrm.audit_context import current_audit_context
from gcrm.db.connection import db
from gcrm.sync.conflict_resolution import (
    FieldVersion,
    is_incoming_version_newer,
    is_valid_edit_time,
)
from gcrm.sync.contracts import SyncUpdate
from gcrm.sync.validation import PRIVATE_FIELDS, validate_sync_patch
from gcrm.tools.db_sync_bootstrap import find_sync_entity
from gcrm.tools.db_sync_private import apply_private_winners, private_winners
from gcrm.tools.deal_records import check_next_step, write_next_step

TABLES = {"organization": "contacts", "person": "people", "deal": "deals",
          "person_note": "people_interactions", "organization_activity": "interactions"}


def _request_hash(update: SyncUpdate) -> str:
    request = json.dumps(update.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(request.encode()).hexdigest()


def _authorize_device(cursor, workspace_id: int, user_id: int, environment: str, update: SyncUpdate) -> None:
    cursor.execute("SELECT 1 FROM mobile_sync_devices WHERE workspace_id=%s AND user_id=%s AND device_id=%s "
                   "AND server_environment=%s AND revoked_at IS NULL FOR SHARE",
                   (workspace_id, user_id, str(update.device_id), environment))
    if cursor.fetchone() is None:
        raise PermissionError("Sync device is unregistered or revoked")


def _replay(cursor, workspace_id: int, user_id: int, update: SyncUpdate, request_hash: str) -> dict | None:
    cursor.execute("SELECT user_id,request_hash,status,winning_fields,ignored_fields FROM sync_mutations "
                   "WHERE workspace_id=%s AND device_id=%s AND mutation_id=%s",
                   (workspace_id, str(update.device_id), str(update.mutation_id)))
    existing = cursor.fetchone()
    if not existing:
        return None
    if existing["user_id"] != user_id:
        raise PermissionError("Mutation belongs to another account")
    if existing["request_hash"] != request_hash:
        raise ValueError("mutation ID was reused with different content")
    if existing["status"] != "erased" and _lock_entity(cursor, workspace_id, update) is None:
        reason, _ = _classify_missing(cursor, workspace_id, update)
        if reason == "erased":
            cursor.execute("UPDATE sync_mutations SET status='erased' WHERE workspace_id=%s AND device_id=%s AND mutation_id=%s",
                           (workspace_id, str(update.device_id), str(update.mutation_id)))
            audit = current_audit_context()
            cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                           "VALUES (%s,%s,'sync.mutation_erased',%s,'erased',%s)",
                           (audit.actor, audit.actor_type, f"sync:{update.entity_kind}:{update.entity_sync_id}", audit.correlation_id))
            existing["status"] = "erased"
    return _response(cursor, workspace_id, user_id, update, existing["status"],
                     existing["winning_fields"], existing["ignored_fields"])


def _response(cursor, workspace_id: int, user_id: int, update: SyncUpdate, status: str,
              winning: list[str], ignored: list[str]) -> dict:
    entity = find_sync_entity(cursor, workspace_id, user_id, update.entity_kind, str(update.entity_sync_id))
    response = {"mutation_id": str(update.mutation_id), "status": status,
                "winning_fields": winning, "ignored_fields": ignored, "entity": entity}
    if entity is None and status in ("applied", "partially_applied", "ignored_older"):
        cursor.execute("SELECT operation,changed_at,merge_target_sync_id FROM sync_entity_changes "
                       "WHERE workspace_id=%s AND entity_kind=%s AND entity_sync_id=%s "
                       "AND target_user_id IS NULL ORDER BY sequence DESC LIMIT 1",
                       (workspace_id, update.entity_kind, str(update.entity_sync_id)))
        marker = cursor.fetchone()
        if marker and marker["operation"] in ("soft_delete", "merge_redirect"):
            response["target_state"] = dict(marker)
    return response


def _record_outcome(cursor, workspace_id: int, user_id: int, update: SyncUpdate, request_hash: str,
                    status: str, winning: list[str], ignored: list[str], server_id: int | None) -> None:
    audit = current_audit_context()
    if audit is None:
        raise RuntimeError("Sync mutation requires an audit identity")
    cursor.execute("INSERT INTO sync_mutations(workspace_id,user_id,device_id,mutation_id,entity_kind,entity_sync_id,operation,"
                   "request_hash,status,winning_fields,ignored_fields,server_id,actor,correlation_id) "
                   "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (workspace_id, user_id, str(update.device_id), str(update.mutation_id), update.entity_kind,
                    str(update.entity_sync_id), update.operation, request_hash, status, winning, ignored, server_id,
                    audit.actor, audit.correlation_id))
    cursor.execute("INSERT INTO audit_log(actor,actor_type,action,target,outcome,correlation_id) "
                   "VALUES (%s,%s,'sync.mutation',%s,%s,%s)",
                   (audit.actor, audit.actor_type, f"sync:{update.entity_kind}:{update.entity_sync_id}",
                    status, audit.correlation_id))


def _lock_entity(cursor, workspace_id: int, update: SyncUpdate):
    cursor.execute(sql.SQL("SELECT * FROM {} WHERE workspace_id=%s AND sync_id=%s FOR UPDATE")
                   .format(sql.Identifier(TABLES[update.entity_kind])),
                   (workspace_id, str(update.entity_sync_id)))
    return cursor.fetchone()


def _classify_missing(cursor, workspace_id: int, update: SyncUpdate) -> tuple[str, str | None]:
    cursor.execute("SELECT operation,merge_target_sync_id FROM sync_entity_changes WHERE workspace_id=%s "
                   "AND entity_kind=%s AND entity_sync_id=%s AND target_user_id IS NULL "
                   "ORDER BY sequence DESC LIMIT 1", (workspace_id, update.entity_kind, str(update.entity_sync_id)))
    marker = cursor.fetchone()
    if marker and marker["operation"] == "hard_erase":
        return "erased", None
    if marker and marker["operation"] == "merge_redirect":
        return _resolve_merge_target(cursor, workspace_id, marker["merge_target_sync_id"])
    return "missing", None


def _resolve_merge_target(cursor, workspace_id: int, target) -> tuple[str, str | None]:
    seen = set()
    while target is not None and str(target) not in seen:
        target = str(target)
        seen.add(target)
        cursor.execute("SELECT sync_id FROM people WHERE workspace_id=%s AND sync_id=%s FOR UPDATE", (workspace_id, target))
        if cursor.fetchone():
            return "merged", target
        cursor.execute("SELECT operation,merge_target_sync_id FROM sync_entity_changes "
                       "WHERE workspace_id=%s AND entity_kind='person' AND entity_sync_id=%s "
                       "AND target_user_id IS NULL ORDER BY sequence DESC LIMIT 1", (workspace_id, target))
        marker = cursor.fetchone()
        if not marker or marker["operation"] not in ("merge_redirect", "hard_erase"):
            return "missing", None
        if marker["operation"] == "hard_erase":
            return "erased", None
        target = marker["merge_target_sync_id"]
    return "missing", None


def _store_provisional(cursor, workspace_id: int, user_id: int, update: SyncUpdate,
                       patch: dict, reason: str, target: str | None,
                       parent_kind: str | None = None, parent_sync_id: str | None = None) -> None:
    recorded = datetime.now(UTC)
    cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                   "entity_sync_id,reason,patch,changed_at,recorded_at,expires_at,merge_target_sync_id,parent_kind,parent_sync_id) "
                   "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (workspace_id, user_id, str(update.device_id), str(update.mutation_id), update.entity_kind,
                    str(update.entity_sync_id), reason, Json(patch), update.changed_at, recorded,
                    recorded + timedelta(days=30), target, parent_kind, parent_sync_id))


def _split_winning_fields(cursor, workspace_id: int, user_id: int, update: SyncUpdate, patch: dict) -> tuple[list[str], list[str]]:
    private = sorted(set(patch) & PRIVATE_FIELDS.get(update.entity_kind, set()))
    shared = sorted(set(patch) - set(private))
    cursor.execute("SELECT field_name,changed_at,device_id,mutation_id FROM sync_field_versions "
                   "WHERE workspace_id=%s AND entity_kind=%s AND entity_sync_id=%s AND field_name=ANY(%s)",
                   (workspace_id, update.entity_kind, str(update.entity_sync_id), shared))
    versions = {row["field_name"]: FieldVersion(row["changed_at"], UUID(str(row["device_id"])),
                                                 UUID(str(row["mutation_id"]))) for row in cursor.fetchall()}
    incoming = FieldVersion(update.changed_at, update.device_id, update.mutation_id)
    winning = [field for field in shared if field not in versions or is_incoming_version_newer(incoming, versions[field])]
    if private:
        private_winning, _ = private_winners(cursor, workspace_id, user_id, update, private)
        winning.extend(private_winning)
    winning.sort()
    return winning, sorted(set(patch) - set(winning))


def _apply_winners(cursor, workspace_id: int, user_id: int, update: SyncUpdate, patch: dict, winning: list[str], entity) -> None:
    if not winning:
        return
    cursor.execute("SELECT set_config('app.sync_changed_at',%s,true),set_config('app.sync_device_id',%s,true),"
                   "set_config('app.sync_mutation_id',%s,true)",
                   (update.changed_at.isoformat(), str(update.device_id), str(update.mutation_id)))
    shared = [field for field in winning if field not in PRIVATE_FIELDS.get(update.entity_kind, set())]
    changed = [field for field in shared if _value_changed(entity[field], patch[field])]
    ordinary = [field for field in shared if update.entity_kind != "deal" or field not in ("next_step", "next_step_date")]
    if update.entity_kind == "deal" and any(field in changed for field in ("next_step", "next_step_date")):
        text, due = _desired_next_step(entity, patch, winning)
        write_next_step(cursor, entity, text, due)
    if ordinary:
        assignments = sql.SQL(", ").join(sql.SQL("{}=%s").format(sql.Identifier(field)) for field in ordinary)
        cursor.execute(sql.SQL("UPDATE {} SET {},updated_at=clock_timestamp() WHERE workspace_id=%s AND sync_id=%s")
                       .format(sql.Identifier(TABLES[update.entity_kind]), assignments),
                       [patch[field] for field in ordinary] + [workspace_id, str(update.entity_sync_id)])
    for field in shared:
        cursor.execute("INSERT INTO sync_field_versions(workspace_id,entity_kind,entity_sync_id,field_name,changed_at,device_id,mutation_id,source) "
                       "VALUES (%s,%s,%s,%s,%s,%s,%s,'mobile') ON CONFLICT (workspace_id,entity_kind,entity_sync_id,field_name) "
                       "DO UPDATE SET changed_at=EXCLUDED.changed_at,device_id=EXCLUDED.device_id,mutation_id=EXCLUDED.mutation_id,source='mobile'",
                       (workspace_id, update.entity_kind, str(update.entity_sync_id), field, update.changed_at,
                        str(update.device_id), str(update.mutation_id)))
    apply_private_winners(cursor, workspace_id, user_id, update, patch, winning, entity)
    if shared and not changed:
        audit = current_audit_context()
        cursor.execute("INSERT INTO sync_entity_changes(workspace_id,entity_kind,entity_sync_id,operation,changed_at,device_id,mutation_id,actor,correlation_id) "
                       "VALUES (%s,%s,%s,'upsert',%s,%s,%s,%s,%s)",
                       (workspace_id, update.entity_kind, str(update.entity_sync_id), update.changed_at,
                        str(update.device_id), str(update.mutation_id), audit.actor, audit.correlation_id))


def _value_changed(existing, incoming) -> bool:
    if isinstance(existing, date) and isinstance(incoming, str):
        return existing.isoformat() != incoming
    return existing != incoming


def _desired_next_step(entity, patch: dict, winning: list[str]) -> tuple[str, date | None]:
    text = patch["next_step"] if "next_step" in winning else entity["next_step"]
    due = patch["next_step_date"] if "next_step_date" in winning else entity["next_step_date"]
    if isinstance(due, str):
        due = date.fromisoformat(due)
    return check_next_step(text, due), due


def _apply_new_update(cursor, workspace_id: int, user_id: int, update: SyncUpdate, request_hash: str) -> dict:
    try:
        patch = validate_sync_patch(update.entity_kind, update.patch)
        status = "rejected_clock" if not is_valid_edit_time(update.changed_at, datetime.now(UTC)) else ""
    except ValueError:
        patch, status = {}, "rejected_validation"
    entity = _lock_entity(cursor, workspace_id, update) if not status else None
    winning, ignored, target = [], [], None
    if not status:
        reason, target = ("soft_deleted", None) if entity and entity["deleted_at"] else (
            ("", None) if entity else _classify_missing(cursor, workspace_id, update))
        if reason in ("soft_deleted", "merged"):
            _store_provisional(cursor, workspace_id, user_id, update, patch, reason, target)
            status = "provisional"
        elif reason:
            status = "erased" if reason == "erased" else "rejected_validation"
        else:
            winning, ignored = _split_winning_fields(cursor, workspace_id, user_id, update, patch)
            try:
                if update.entity_kind == "deal" and any(field in winning for field in ("next_step", "next_step_date")):
                    _desired_next_step(entity, patch, winning)
            except ValueError:
                status, winning, ignored = "rejected_validation", [], []
            else:
                _apply_winners(cursor, workspace_id, user_id, update, patch, winning, entity)
                status = "partially_applied" if winning and ignored else "applied" if winning else "ignored_older"
    _record_outcome(cursor, workspace_id, user_id, update, request_hash, status, winning, ignored, entity["id"] if entity else None)
    return _response(cursor, workspace_id, user_id, update, status, winning, ignored)


def apply_sync_update(workspace_id: int, user_id: int, environment: str, update: SyncUpdate) -> dict:
    request_hash = _request_hash(update)
    with db() as connection:
        cursor = connection.cursor()
        _authorize_device(cursor, workspace_id, user_id, environment, update)
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                       (f"{workspace_id}:{update.device_id}:{update.mutation_id}",))
        replay = _replay(cursor, workspace_id, user_id, update, request_hash)
        return replay if replay is not None else _apply_new_update(cursor, workspace_id, user_id, update, request_hash)
