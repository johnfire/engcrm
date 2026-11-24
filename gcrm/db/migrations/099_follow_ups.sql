-- Independent follow-ups; historical entries are reviewed before activation.
CREATE TABLE follow_ups (
    id BIGSERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
    contact_person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    deal_id INTEGER REFERENCES deals(id) ON DELETE CASCADE,
    task_type TEXT CHECK (task_type IN ('commitment', 'check_in')),
    task_text TEXT NOT NULL DEFAULT '',
    due_date DATE,
    status TEXT NOT NULL DEFAULT 'review' CHECK (status IN ('review', 'active', 'completed', 'dismissed', 'linked')),
    source_kind TEXT CHECK (source_kind IN ('deal', 'interaction')),
    source_id INTEGER,
    source_date DATE,
    linked_task_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    CHECK ((contact_id IS NULL) <> (person_id IS NULL)),
    CHECK (contact_person_id IS NULL OR contact_id IS NOT NULL),
    CHECK ((source_kind IS NULL) = (source_id IS NULL)),
    CHECK (status <> 'active' OR (task_type IS NOT NULL AND length(trim(task_text)) > 0)),
    CHECK ((status = 'linked') = (linked_task_id IS NOT NULL)),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, linked_task_id) REFERENCES follow_ups(workspace_id, id)
);

CREATE UNIQUE INDEX follow_ups_source ON follow_ups (workspace_id, source_kind, source_id)
    WHERE source_kind IS NOT NULL;
CREATE INDEX follow_ups_active_date ON follow_ups (workspace_id, due_date, id)
    WHERE status = 'active';

-- Snapshot old sources before any subsequent legacy write can change them.
INSERT INTO follow_ups (workspace_id, contact_id, person_id, contact_person_id,
                        deal_id, task_text, due_date, source_kind, source_id, source_date)
SELECT workspace_id, contact_id, person_id, contact_person_id, id,
       COALESCE(next_step, ''), next_step_date, 'deal', id, updated_at::date
  FROM deals WHERE deleted_at IS NULL
   AND (NULLIF(trim(next_step), '') IS NOT NULL OR next_step_date IS NOT NULL)
ON CONFLICT DO NOTHING;

INSERT INTO follow_ups (workspace_id, contact_id, deal_id, task_text, due_date, source_kind, source_id, source_date)
SELECT i.workspace_id, i.contact_id, d.id, COALESCE(i.next_action, ''), i.next_action_date, 'interaction', i.id,
       i.interaction_date
  FROM interactions i
  LEFT JOIN deals d ON d.contact_id = i.contact_id AND d.offer_id = i.offer_id
                   AND d.workspace_id = i.workspace_id AND d.deleted_at IS NULL
 WHERE i.deleted_at IS NULL AND i.method IS DISTINCT FROM 'next_step'
   AND i.method IS DISTINCT FROM 'next_step_done'
   AND (NULLIF(trim(i.next_action), '') IS NOT NULL OR i.next_action_date IS NOT NULL)
ON CONFLICT DO NOTHING;

ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY;
ALTER TABLE follow_ups FORCE ROW LEVEL SECURITY;
CREATE POLICY follow_ups_workspace ON follow_ups TO engcrm_workspace
    USING (workspace_id = request_workspace_id())
    WITH CHECK (workspace_id = request_workspace_id()
        AND (contact_id IS NULL OR EXISTS (SELECT 1 FROM contacts c WHERE c.id = contact_id))
        AND (person_id IS NULL OR EXISTS (SELECT 1 FROM people p WHERE p.id = person_id))
        AND (contact_person_id IS NULL OR EXISTS (
            SELECT 1 FROM people p WHERE p.id = contact_person_id AND p.contact_id = follow_ups.contact_id))
        AND (deal_id IS NULL OR EXISTS (
            SELECT 1 FROM deals d WHERE d.id = deal_id
              AND d.contact_id IS NOT DISTINCT FROM follow_ups.contact_id
              AND d.person_id IS NOT DISTINCT FROM follow_ups.person_id))
        AND (source_kind IS NULL OR (source_kind = 'deal' AND EXISTS (
                 SELECT 1 FROM deals source_deal WHERE source_deal.id = source_id
                   AND source_deal.contact_id IS NOT DISTINCT FROM follow_ups.contact_id
                   AND source_deal.person_id IS NOT DISTINCT FROM follow_ups.person_id))
             OR (source_kind = 'interaction' AND EXISTS (
                 SELECT 1 FROM interactions i WHERE i.id = source_id AND i.contact_id = follow_ups.contact_id))));
GRANT SELECT, INSERT, UPDATE, DELETE ON follow_ups TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE follow_ups_id_seq TO engcrm_workspace;
