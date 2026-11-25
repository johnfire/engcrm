"""Read bounded, explicitly projected pages for the first mobile sync."""

from gcrm.db.connection import db
from gcrm.sync.validation import PRIVATE_FIELDS

PROJECTIONS = (
    ("organization", "contacts", "t.name,t.type,t.city,t.country,t.address,t.website,t.email,t.phone,"
     "t.preferred_language,t.fit_score,t.best_visit_time,t.access_notes,t.space_notes,t.price_sensitivity,"
     "t.decision_maker,t.preferred_contact_method,t.latitude,t.longitude,t.notes,t.flagged,t.starred,t.source,"
     "t.do_not_contact,t.email_bounced,t.research_exhausted,t.created_at,"
     "rating.priority AS personal_priority,rating.short_term_value,rating.long_term_value",
     "LEFT JOIN contact_user_priorities rating ON rating.contact_id=t.id AND rating.user_id=%s"),
    ("person", "people", "t.name,t.email,t.preferred_language,t.notes,t.city,t.country,t.phone,t.website,"
     "t.relationship,t.title,t.source,t.met_at,t.is_linkedin_contact,t.linkedin_url,t.connected_on,"
     "t.company_raw,t.retention_hold,t.pending_company_raw,t.pending_title,t.latitude,t.longitude,t.created_at,"
     "organization.sync_id AS organization_sync_id,rating.priority AS value_rating,"
     "rating.short_term_value,rating.long_term_value",
     "LEFT JOIN contacts organization ON organization.id=t.contact_id AND organization.deleted_at IS NULL "
     "LEFT JOIN person_user_priorities rating ON rating.person_id=t.id AND rating.user_id=%s"),
    ("deal", "deals", "t.pipeline_stage,t.status,t.next_step,t.next_step_date,t.notes,t.created_at,"
     "(SELECT COALESCE(SUM(s.amount_eur),0) FROM sales s WHERE s.deal_id=t.id AND s.deleted_at IS NULL "
     "AND s.status IN ('expected','booked','contracted','collected')) AS total_value,"
     "offer.slug AS offer_slug,offer.name AS offer_name,organization.sync_id AS organization_sync_id,"
     "person.sync_id AS person_sync_id,contact_person.sync_id AS contact_person_sync_id",
     "JOIN offers offer ON offer.id=t.offer_id LEFT JOIN contacts organization ON organization.id=t.contact_id "
     "LEFT JOIN people person ON person.id=t.person_id "
     "LEFT JOIN people contact_person ON contact_person.id=t.contact_person_id"),
    ("organization_activity", "interactions", "t.interaction_date,t.method,t.direction,t.summary,t.outcome,"
     "t.next_action,t.next_action_date,t.duration_minutes,t.impression,t.materials_left,t.attitude,t.my_read,"
     "t.created_at,organization.sync_id AS organization_sync_id,offer.slug AS offer_slug",
     "JOIN contacts organization ON organization.id=t.contact_id AND organization.deleted_at IS NULL "
     "LEFT JOIN offers offer ON offer.id=t.offer_id"),
    ("person_note", "people_interactions", "t.occurred_at,t.method,t.note,t.duration_minutes,t.attitude,"
     "t.my_read,t.created_at,person.sync_id AS person_sync_id,offer.slug AS offer_slug",
     "JOIN people person ON person.id=t.person_id AND person.deleted_at IS NULL "
     "LEFT JOIN offers offer ON offer.id=t.offer_id"),
)


def read_bootstrap_page(workspace_id: int, user_id: int, device_id: str, environment: str,
                        position: dict | None, limit: int) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM mobile_sync_devices WHERE workspace_id=%s AND user_id=%s "
                       "AND device_id=%s AND server_environment=%s AND revoked_at IS NULL",
                       (workspace_id, user_id, device_id, environment))
        if cursor.fetchone() is None:
            return None
        if position is None:
            cursor.execute("SELECT pg_advisory_xact_lock(1937337955, %s)", (workspace_id,))
            cursor.execute("SELECT COALESCE((SELECT last_sequence FROM sync_workspace_cursors "
                           "WHERE workspace_id=%s),0) AS high_water", (workspace_id,))
            position = {"kind": 0, "after": 0, "high_water": cursor.fetchone()["high_water"]}
        entries, next_position = _read_page(cursor, workspace_id, user_id, position, limit)
        return {"entities": entries, "high_water": position["high_water"], "position": next_position}


def _read_page(cursor, workspace_id: int, user_id: int, position: dict, limit: int) -> tuple[list[dict], dict | None]:
    entries = []
    kind_index, after_id = position["kind"], position["after"]
    while kind_index < len(PROJECTIONS) and len(entries) < limit:
        kind, table, fields, joins = PROJECTIONS[kind_index]
        owner_filter = ""
        if kind == "deal":
            owner_filter = " AND (t.contact_id IS NULL OR organization.deleted_at IS NULL) " \
                           "AND (t.person_id IS NULL OR person.deleted_at IS NULL)"
        arguments = ([user_id] if kind in ("organization", "person") else [])
        arguments.extend([workspace_id, after_id, limit - len(entries)])
        cursor.execute(
            f"SELECT t.id AS server_id,t.sync_id,{fields} FROM {table} t {joins} "
            f"WHERE t.workspace_id=%s AND t.deleted_at IS NULL AND t.id>%s {owner_filter} ORDER BY t.id LIMIT %s",
            arguments,
        )
        rows = cursor.fetchall()
        for row in rows:
            envelope = project_sync_entity(cursor, workspace_id, user_id, kind, row)
            entries.append(envelope)
            after_id = envelope["server_id"]
        if len(entries) < limit:
            kind_index += 1
            after_id = 0
    next_position = {"kind": kind_index, "after": after_id, "high_water": position["high_water"]} if kind_index < len(PROJECTIONS) else None
    return entries, next_position


def project_sync_entity(cursor, workspace_id: int, user_id: int, kind: str, row) -> dict:
    fields = dict(row)
    server_id, sync_id = fields.pop("server_id"), fields.pop("sync_id")
    cursor.execute("SELECT field_name,changed_at,device_id,mutation_id FROM sync_field_versions "
                   "WHERE workspace_id=%s AND entity_kind=%s AND entity_sync_id=%s",
                   (workspace_id, kind, sync_id))
    clocks = {clock["field_name"]: {"changed_at": clock["changed_at"], "device_id": clock["device_id"],
                                     "mutation_id": clock["mutation_id"]} for clock in cursor.fetchall()
              if clock["field_name"] in fields and clock["field_name"] not in PRIVATE_FIELDS.get(kind, set())}
    if PRIVATE_FIELDS.get(kind):
        cursor.execute("SELECT field_name,changed_at,device_id,mutation_id FROM sync_private_field_versions "
                       "WHERE workspace_id=%s AND user_id=%s AND entity_kind=%s AND entity_sync_id=%s",
                       (workspace_id, user_id, kind, sync_id))
        clocks.update({clock["field_name"]: {"changed_at": clock["changed_at"], "device_id": clock["device_id"],
                                             "mutation_id": clock["mutation_id"]} for clock in cursor.fetchall()
                       if clock["field_name"] in fields})
    return {"entity_kind": kind, "sync_id": sync_id, "server_id": server_id,
            "fields": fields, "field_versions": clocks}


def find_sync_entity(cursor, workspace_id: int, user_id: int, kind: str, sync_id) -> dict | None:
    projection = next((entry for entry in PROJECTIONS if entry[0] == kind), None)
    if projection is None:
        return None
    _, table, fields, joins = projection
    owner_filter = ""
    if kind == "deal":
        owner_filter = " AND (t.contact_id IS NULL OR organization.deleted_at IS NULL) " \
                       "AND (t.person_id IS NULL OR person.deleted_at IS NULL)"
    arguments = [user_id] if kind in ("organization", "person") else []
    arguments.extend([workspace_id, sync_id])
    cursor.execute(f"SELECT t.id AS server_id,t.sync_id,{fields} FROM {table} t {joins} "
                   f"WHERE t.workspace_id=%s AND t.sync_id=%s AND t.deleted_at IS NULL {owner_filter}", arguments)
    row = cursor.fetchone()
    return project_sync_entity(cursor, workspace_id, user_id, kind, row) if row else None
