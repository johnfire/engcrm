-- Migration 060: what statistics need — sales in €, time per activity, and a
-- history of stage changes. See docs/plans/2026-10-05-statistics-design.md.

-- Sales won from an organization. Soft-deleted like the rest of the CRM.
CREATE TABLE IF NOT EXISTS sales (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    contact_id   INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    amount_eur   NUMERIC(12, 2) NOT NULL CHECK (amount_eur > 0),
    won_on       DATE NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sales_won_on ON sales (workspace_id, won_on) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sales_contact ON sales (contact_id) WHERE deleted_at IS NULL;

-- Time an activity took, when typed in. Blank means "the type's default".
ALTER TABLE interactions        ADD COLUMN IF NOT EXISTS duration_minutes INTEGER CHECK (duration_minutes >= 0);
ALTER TABLE people_interactions ADD COLUMN IF NOT EXISTS duration_minutes INTEGER CHECK (duration_minutes >= 0);

-- The default minutes per activity type, editable per workspace in Settings.
CREATE TABLE IF NOT EXISTS activity_minute_defaults (
    workspace_id  INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL CHECK (activity_type IN ('drop_in', 'meeting', 'phone', 'video', 'email', 'note')),
    minutes       INTEGER NOT NULL CHECK (minutes >= 0),
    PRIMARY KEY (workspace_id, activity_type)
);
INSERT INTO activity_minute_defaults (workspace_id, activity_type, minutes)
SELECT w.id, d.activity_type, d.minutes
  FROM workspaces w
 CROSS JOIN (VALUES ('drop_in', 15), ('meeting', 45), ('phone', 15),
                    ('video', 30), ('email', 10), ('note', 0)) AS d(activity_type, minutes)
ON CONFLICT DO NOTHING;

-- Every stage change, whichever screen, script or agent made it. Written by the
-- triggers below, so no write path can forget it.
CREATE TABLE IF NOT EXISTS stage_changes (
    id           BIGSERIAL PRIMARY KEY,
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('organization', 'person')),
    entity_id    INTEGER NOT NULL,
    workspace_id INTEGER,
    from_stage   TEXT,
    to_stage     TEXT,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stage_changes_when ON stage_changes (workspace_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_stage_changes_entity ON stage_changes (entity_type, entity_id);

CREATE OR REPLACE FUNCTION record_stage_change() RETURNS trigger AS $$
BEGIN
    INSERT INTO stage_changes (entity_type, entity_id, workspace_id, from_stage, to_stage)
    VALUES (TG_ARGV[0], NEW.id, NEW.workspace_id, OLD.pipeline_stage, NEW.pipeline_stage);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS contacts_stage_history ON contacts;
CREATE TRIGGER contacts_stage_history
    AFTER UPDATE OF pipeline_stage ON contacts
    FOR EACH ROW WHEN (NEW.pipeline_stage IS DISTINCT FROM OLD.pipeline_stage)
    EXECUTE FUNCTION record_stage_change('organization');

DROP TRIGGER IF EXISTS people_stage_history ON people;
CREATE TRIGGER people_stage_history
    AFTER UPDATE OF pipeline_stage ON people
    FOR EACH ROW WHEN (NEW.pipeline_stage IS DISTINCT FROM OLD.pipeline_stage)
    EXECUTE FUNCTION record_stage_change('person');
