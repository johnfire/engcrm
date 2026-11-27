"""Search the follow-up and historical-review queues."""
from datetime import date

from gcrm.db.connection import db


def list_follow_up_targets(workspace_id: int | None = None) -> list[dict]:
    """Offer deals and general owners as explicit task targets."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT 'deal:' || d.id AS target, COALESCE(c.name,p.name) || ' · ' || o.name AS label,
                      d.contact_id, d.person_id, d.id AS deal_id
                 FROM deals d JOIN offers o ON o.id=d.offer_id
                 LEFT JOIN contacts c ON c.id=d.contact_id AND c.deleted_at IS NULL
                 LEFT JOIN people p ON p.id=d.person_id AND p.deleted_at IS NULL
                WHERE d.deleted_at IS NULL AND COALESCE(c.id,p.id) IS NOT NULL
                  AND (%s IS NULL OR d.workspace_id=%s)
               UNION ALL
               SELECT 'organization:' || c.id, c.name, c.id, NULL::integer, NULL::integer FROM contacts c
                WHERE c.deleted_at IS NULL AND (%s IS NULL OR c.workspace_id=%s)
               UNION ALL
               SELECT 'person:' || p.id, p.name, NULL::integer, p.id, NULL::integer FROM people p
                WHERE p.deleted_at IS NULL AND (%s IS NULL OR p.workspace_id=%s)
               ORDER BY label, target""", (workspace_id, workspace_id, workspace_id, workspace_id,
                                               workspace_id, workspace_id),
        )
        return [dict(row) for row in cursor.fetchall()]


def deal_follow_ups(deal_ids: list[int], workspace_id: int | None = None) -> dict[int, list[dict]]:
    """The active follow-ups of these deals, earliest first and undated last, by deal id."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, deal_id, task_type, task_text, due_date, updated_at FROM follow_ups "
                       "WHERE status='active' AND deal_id=ANY(%s) AND (%s IS NULL OR workspace_id=%s) "
                       "ORDER BY due_date ASC NULLS LAST, id", (list(deal_ids), workspace_id, workspace_id))
        found: dict[int, list[dict]] = {}
        for row in cursor.fetchall():
            found.setdefault(row["deal_id"], []).append(dict(row))
        return found


def list_follow_up_people(workspace_id: int | None = None) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT p.id, p.name, p.contact_id, c.name AS organization_name FROM people p "
                       "JOIN contacts c ON c.id=p.contact_id AND c.deleted_at IS NULL "
                       "WHERE p.deleted_at IS NULL AND (%s IS NULL OR p.workspace_id=%s) "
                       "ORDER BY lower(c.name), lower(p.name), p.id", (workspace_id, workspace_id))
        return [dict(row) for row in cursor.fetchall()]


def find_follow_ups(*, workspace_id: int | None = None, search: str = "", task_type: str = "",
                    stage: str = "", offer_id: int | None = None, date_from: date | None = None,
                    date_to: date | None = None, direction: str = "asc", status: str = "active",
                    limit: int = 25, offset: int = 0, task_id: int | None = None) -> list[dict]:
    if direction not in ("asc", "desc") or status not in ("active", "review"):
        raise ValueError("Invalid follow-up view")
    if task_type not in ("", "commitment", "check_in"):
        raise ValueError("Invalid follow-up type")
    order = "ASC" if direction == "asc" else "DESC"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT f.*, c.name AS organization_name, p.name AS person_name,
                   pc.id AS person_organization_id, pc.name AS person_organization_name,
                   cp.name AS contact_person_name, o.name AS offer_name, source_offer.name AS source_offer_name,
                   d.pipeline_stage, d.status AS deal_status
              FROM follow_ups f
              LEFT JOIN contacts c ON c.id=f.contact_id
              LEFT JOIN people p ON p.id=f.person_id
              LEFT JOIN contacts pc ON pc.id=p.contact_id AND pc.deleted_at IS NULL
              LEFT JOIN people cp ON cp.id=f.contact_person_id
              LEFT JOIN deals d ON d.id=f.deal_id
              LEFT JOIN interactions i ON f.source_kind='interaction' AND i.id=f.source_id
              LEFT JOIN offers source_offer ON source_offer.id=i.offer_id
              LEFT JOIN offers o ON o.id=COALESCE(d.offer_id, i.offer_id)
             WHERE f.status=%(status)s AND (%(workspace)s IS NULL OR f.workspace_id=%(workspace)s)
               AND ((c.id IS NOT NULL AND c.deleted_at IS NULL) OR (p.id IS NOT NULL AND p.deleted_at IS NULL))
               AND (%(task_id)s IS NULL OR f.id=%(task_id)s)
               AND (%(task_type)s='' OR f.task_type=%(task_type)s)
               AND (%(stage)s='' OR d.pipeline_stage=%(stage)s)
               AND (%(offer)s IS NULL OR COALESCE(d.offer_id, i.offer_id)=%(offer)s)
               AND (f.due_date IS NULL OR (%(date_from)s IS NULL OR f.due_date >= %(date_from)s)
                                         AND (%(date_to)s IS NULL OR f.due_date <= %(date_to)s))
               AND (f.task_text ILIKE %(search)s OR c.name ILIKE %(search)s OR p.name ILIKE %(search)s
                    OR cp.name ILIKE %(search)s OR pc.name ILIKE %(search)s)
             ORDER BY f.due_date {order} NULLS LAST, f.id ASC
             LIMIT %(limit)s OFFSET %(offset)s
            """,
            {"status": status, "workspace": workspace_id, "task_type": task_type, "stage": stage,
             "offer": offer_id, "date_from": date_from, "date_to": date_to, "search": f"%{search}%",
             "limit": limit, "offset": offset, "task_id": task_id},
        )
        return [dict(row) for row in cursor.fetchall()]
