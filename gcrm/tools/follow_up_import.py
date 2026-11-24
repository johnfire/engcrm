"""Import legacy follow-ups without deciding whether they are still owed."""
from gcrm.db.connection import db


def import_legacy_follow_ups() -> None:
    """Retain one durable source reference per legacy deal or activity."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO follow_ups (workspace_id, contact_id, person_id, contact_person_id,
                                    deal_id, task_text, due_date, source_kind, source_id, source_date)
            SELECT workspace_id, contact_id, person_id, contact_person_id, id,
                   COALESCE(next_step, ''), next_step_date, 'deal', id, updated_at::date
              FROM deals
             WHERE deleted_at IS NULL AND (NULLIF(trim(next_step), '') IS NOT NULL OR next_step_date IS NOT NULL)
            ON CONFLICT DO NOTHING
            """
        )
        cursor.execute(
            """
            INSERT INTO follow_ups (workspace_id, contact_id, deal_id, task_text, due_date, source_kind, source_id, source_date)
            SELECT i.workspace_id, i.contact_id, d.id, COALESCE(i.next_action, ''), i.next_action_date,
                   'interaction', i.id, i.interaction_date
              FROM interactions i
              LEFT JOIN deals d ON d.contact_id = i.contact_id AND d.offer_id = i.offer_id
                               AND d.workspace_id = i.workspace_id AND d.deleted_at IS NULL
             WHERE i.deleted_at IS NULL AND i.method IS DISTINCT FROM 'next_step'
               AND i.method IS DISTINCT FROM 'next_step_done'
               AND (NULLIF(trim(i.next_action), '') IS NOT NULL OR i.next_action_date IS NOT NULL)
            ON CONFLICT DO NOTHING
            """
        )
