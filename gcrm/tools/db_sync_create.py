"""Create an offline organization or person exactly once."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from psycopg2 import sql

from gcrm.activity_types import (
    ATTITUDES,
    MY_READS,
    ORGANIZATION_METHODS,
    PERSON_METHODS,
    parse_choices,
    parse_minutes,
)
from gcrm.db.connection import db
from gcrm.sources import MANUAL_MOBILE
from gcrm.sync.conflict_resolution import is_valid_edit_time
from gcrm.sync.contracts import SyncCreate
from gcrm.sync.validation import PRIVATE_FIELDS, validate_sync_patch
from gcrm.tools.db_sync_push import (
    TABLES,
    _authorize_device,
    _classify_missing,
    _lock_entity,
    _record_outcome,
    _replay,
    _request_hash,
    _response,
    _store_provisional,
)
from gcrm.tools.deal_records import _open_deal_offers
from gcrm.tools.follow_ups import record_activity_follow_up


class ParentNeedsReview(Exception):
    def __init__(self, kind: str, sync_id: str, reason: str, target: str | None = None):
        self.kind, self.sync_id, self.reason, self.target = kind, sync_id, reason, target


class ParentErased(Exception):
    pass


def _resolve_parent(cursor, workspace_id: int, kind: str, parent_sync_id) -> int:
    try:
        parent_uuid = str(UUID(str(parent_sync_id)))
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid parent identity") from error
    cursor.execute(sql.SQL("SELECT id,deleted_at FROM {} WHERE workspace_id=%s AND sync_id=%s FOR UPDATE")
                   .format(sql.Identifier(TABLES[kind])), (workspace_id, parent_uuid))
    parent = cursor.fetchone()
    if parent:
        if parent["deleted_at"] is not None:
            raise ParentNeedsReview(kind, parent_uuid, "soft_deleted")
        return parent["id"]
    state, target = _classify_missing(cursor, workspace_id, SimpleNamespace(entity_kind=kind, entity_sync_id=parent_uuid))
    if state == "erased":
        raise ParentErased
    if state == "merged":
        raise ParentNeedsReview(kind, parent_uuid, "merged", target)
    raise ValueError("Linked record is not available")


def _parent_id(cursor, workspace_id: int, parent_sync_id) -> int | None:
    if parent_sync_id is None:
        return None
    return _resolve_parent(cursor, workspace_id, "organization", parent_sync_id)


def _validate_create(cursor, workspace_id: int, user_id: int, creation: SyncCreate) -> dict:
    if creation.entity_kind == "person_note":
        return _person_note_fields(cursor, workspace_id, creation)
    if creation.entity_kind == "organization_activity":
        return _organization_activity_fields(cursor, workspace_id, creation)
    if creation.entity_kind == "deal":
        return _initial_deal_fields(cursor, workspace_id, user_id, creation)
    patch = dict(creation.patch)
    if set(patch) & PRIVATE_FIELDS.get(creation.entity_kind, set()):
        raise ValueError("Private ratings must be saved after creation")
    parent = patch.pop("organization_sync_id", None) if creation.entity_kind == "person" else None
    values = validate_sync_patch(creation.entity_kind, patch)
    if not values.get("name"):
        raise ValueError("Name is required")
    if parent is not None:
        values["contact_id"] = _parent_id(cursor, workspace_id, parent)
    return values


def _initial_deal_fields(cursor, workspace_id: int, user_id: int, creation: SyncCreate) -> dict:
    patch = creation.patch
    allowed = {"organization_sync_id", "person_sync_id", "offer_slug", "pipeline_stage", "status"}
    if set(patch) - allowed or bool(patch.get("organization_sync_id")) == bool(patch.get("person_sync_id")):
        raise ValueError("Choose one owner for the initial deal")
    kind = "organization" if patch.get("organization_sync_id") else "person"
    try:
        owner_uuid = str(UUID(str(patch[f"{kind}_sync_id"])))
    except (KeyError, ValueError) as error:
        raise ValueError("Invalid owner identity") from error
    column = "contact_id" if kind == "organization" else "person_id"
    cursor.execute("SELECT 1 FROM sync_mutations WHERE workspace_id=%s AND user_id=%s AND device_id=%s "
                   "AND entity_kind=%s AND entity_sync_id=%s AND operation='create' AND status='applied'",
                   (workspace_id, user_id, str(creation.device_id), kind, owner_uuid))
    if not cursor.fetchone():
        raise ValueError("Initial deal requires an owner created by this account and device")
    offer = patch.get("offer_slug")
    if not isinstance(offer, str) or not offer:
        raise ValueError("Offer is required")
    cursor.execute("SELECT id FROM offers WHERE workspace_id=%s AND slug=%s AND archived_at IS NULL", (workspace_id, offer))
    offer_row = cursor.fetchone()
    if not offer_row:
        raise ValueError("Unknown offer")
    stage = validate_sync_patch("deal", {"pipeline_stage": patch.get("pipeline_stage", "candidate"),
                                         "status": patch.get("status", "none")})
    owner_id = _resolve_parent(cursor, workspace_id, kind, owner_uuid)
    cursor.execute(sql.SQL("SELECT 1 FROM deals WHERE workspace_id=%s AND {}=%s LIMIT 1").format(sql.Identifier(column)),
                   (workspace_id, owner_id))
    if cursor.fetchone():
        raise ValueError("This owner already has a deal")
    return {column: owner_id, "offer_id": offer_row["id"], **stage}


def _resolve_offer(cursor, workspace_id: int, owner: str, owner_id: int, choice) -> int | None:
    if choice is None:
        offers = _open_deal_offers(cursor, owner, owner_id)
        return offers[0] if len(offers) == 1 else None
    if choice in ("", "general"):
        return None
    if not isinstance(choice, str):
        raise ValueError("Invalid offer")
    cursor.execute("SELECT id FROM offers WHERE workspace_id=%s AND slug=%s AND archived_at IS NULL", (workspace_id, choice))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Unknown offer")
    return row["id"]


def _validate_offer_choice(cursor, workspace_id: int, choice) -> None:
    if choice is None or choice in ("", "general"):
        return
    if not isinstance(choice, str):
        raise ValueError("Invalid offer")
    cursor.execute("SELECT 1 FROM offers WHERE workspace_id=%s AND slug=%s AND archived_at IS NULL", (workspace_id, choice))
    if not cursor.fetchone():
        raise ValueError("Unknown offer")


def _person_note_fields(cursor, workspace_id: int, creation: SyncCreate) -> dict:
    patch = creation.patch
    allowed = {"person_sync_id", "note", "method", "duration_minutes", "offer_slug", "attitude", "my_read"}
    if set(patch) - allowed or not isinstance(patch.get("note"), str) or not patch["note"].strip() or len(patch["note"]) > 20000:
        raise ValueError("Invalid person note")
    try:
        person_sync_id = str(UUID(str(patch.get("person_sync_id"))))
    except ValueError as error:
        raise ValueError("Invalid person identity") from error
    method = patch.get("method")
    if method is not None and method not in PERSON_METHODS:
        raise ValueError("Unknown activity method")
    try:
        minutes = parse_minutes(patch.get("duration_minutes"))
        attitude = parse_choices(patch.get("attitude"), ATTITUDES)
        my_read = parse_choices(patch.get("my_read"), MY_READS)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Invalid note details") from error
    _validate_offer_choice(cursor, workspace_id, patch.get("offer_slug"))
    person_id = _resolve_parent(cursor, workspace_id, "person", person_sync_id)
    return {"person_id": person_id, "note": patch["note"].strip(), "occurred_at": creation.changed_at,
            "method": method, "duration_minutes": minutes,
            "offer_id": _resolve_offer(cursor, workspace_id, "person", person_id, patch.get("offer_slug")),
            "attitude": attitude, "my_read": my_read}


def _organization_activity_fields(cursor, workspace_id: int, creation: SyncCreate) -> dict:
    patch = creation.patch
    allowed = {"organization_sync_id", "summary", "method", "duration_minutes", "offer_slug", "attitude", "my_read",
               "interaction_date", "materials_left", "next_action", "next_action_date", "follow_up_type"}
    if set(patch) - allowed or not isinstance(patch.get("summary"), str) or not patch["summary"].strip() or len(patch["summary"]) > 20000:
        raise ValueError("Invalid organization activity")
    method = patch.get("method")
    if method is not None and method not in ORGANIZATION_METHODS:
        raise ValueError("Unknown activity method")
    follow_type = patch.get("follow_up_type")
    if follow_type not in (None, "commitment", "check_in"):
        raise ValueError("Unknown follow-up type")
    try:
        occurred = date.fromisoformat(patch["interaction_date"]) if patch.get("interaction_date") else creation.changed_at.date()
        if occurred > creation.changed_at.date() + timedelta(days=1):
            raise ValueError("Activity date is in the future")
        due = date.fromisoformat(patch["next_action_date"]) if patch.get("next_action_date") else None
        action = patch.get("next_action")
        if action is not None and (not isinstance(action, str) or len(action) > 500):
            raise ValueError("Invalid follow-up text")
        minutes = parse_minutes(patch.get("duration_minutes"))
        attitude = parse_choices(patch.get("attitude"), ATTITUDES)
        my_read = parse_choices(patch.get("my_read"), MY_READS)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Invalid activity details") from error
    materials = patch.get("materials_left")
    if materials is not None and (not isinstance(materials, str) or len(materials) > 20000):
        raise ValueError("Invalid materials")
    _validate_offer_choice(cursor, workspace_id, patch.get("offer_slug"))
    organization = _parent_id(cursor, workspace_id, patch.get("organization_sync_id"))
    if organization is None:
        raise ValueError("Organization is required")
    return {"contact_id": organization, "summary": patch["summary"].strip(), "interaction_date": occurred,
            "method": method, "outcome": "note", "duration_minutes": minutes, "attitude": attitude, "my_read": my_read,
            "materials_left": materials, "next_action": action.strip() or None if action is not None else None,
            "next_action_date": due, "offer_id": _resolve_offer(cursor, workspace_id, "organization", organization, patch.get("offer_slug"))}


def _insert_created(cursor, workspace_id: int, creation: SyncCreate, values: dict) -> int:
    cursor.execute("SELECT set_config('app.sync_changed_at',%s,true),set_config('app.sync_device_id',%s,true),"
                   "set_config('app.sync_mutation_id',%s,true)",
                   (creation.changed_at.isoformat(), str(creation.device_id), str(creation.mutation_id)))
    source = ["source"] if creation.entity_kind in ("organization", "person") else []
    columns = ["workspace_id", "sync_id", *source, *values]
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
        sql.Identifier(TABLES[creation.entity_kind]), sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(sql.Placeholder() for _ in columns),
    )
    cursor.execute(query, [workspace_id, str(creation.entity_sync_id), *([MANUAL_MOBILE] if source else []), *values.values()])
    created_id = cursor.fetchone()["id"]
    if creation.entity_kind == "organization_activity":
        record_activity_follow_up(cursor, created_id, creation.patch.get("follow_up_type"))
    return created_id


def _apply_creation(cursor, workspace_id: int, user_id: int, creation: SyncCreate, request_hash: str) -> dict:
    status, values = "", {}
    try:
        if not is_valid_edit_time(creation.changed_at, datetime.now(UTC)):
            status = "rejected_clock"
        else:
            values = _validate_create(cursor, workspace_id, user_id, creation)
    except ParentNeedsReview as review:
        _store_provisional(cursor, workspace_id, user_id, creation, creation.patch, review.reason,
                           review.target, review.kind, review.sync_id)
        status = "provisional"
    except ParentErased:
        status = "erased"
    except ValueError:
        status = "rejected_validation"
    existing = _lock_entity(cursor, workspace_id, creation) if not status else None
    if existing:
        status = "rejected_validation"
    if not status:
        prior, _ = _classify_missing(cursor, workspace_id, creation)
        if prior == "erased":
            status = "erased"
        elif prior != "missing":
            status = "rejected_validation"
    server_id = _insert_created(cursor, workspace_id, creation, values) if not status else None
    if not status:
        status = "applied"
    _record_outcome(cursor, workspace_id, user_id, creation, request_hash, status, sorted(values) if server_id else [], [], server_id)
    return _response(cursor, workspace_id, user_id, creation, status, sorted(values) if server_id else [], [])


def apply_sync_create(workspace_id: int, user_id: int, environment: str, creation: SyncCreate) -> dict:
    request_hash = _request_hash(creation)
    with db() as connection:
        cursor = connection.cursor()
        _authorize_device(cursor, workspace_id, user_id, environment, creation)
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                       (f"{workspace_id}:{creation.device_id}:{creation.mutation_id}",))
        replay = _replay(cursor, workspace_id, user_id, creation, request_hash)
        return replay if replay is not None else _apply_creation(cursor, workspace_id, user_id, creation, request_hash)
