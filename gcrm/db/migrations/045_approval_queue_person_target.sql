-- Let approval_queue hold drafts targeted at a person (not just an organization),
-- so the person-scoped curiosity first-contact email can land in the same
-- Drafts review page as the org sales-outreach drafts. Exactly one of
-- contact_id / person_id is set per row.

ALTER TABLE approval_queue ALTER COLUMN contact_id DROP NOT NULL;
ALTER TABLE approval_queue ADD COLUMN IF NOT EXISTS person_id INTEGER REFERENCES people(id) ON DELETE CASCADE;

ALTER TABLE approval_queue DROP CONSTRAINT IF EXISTS chk_approval_queue_one_target;
ALTER TABLE approval_queue ADD CONSTRAINT chk_approval_queue_one_target
    CHECK ((contact_id IS NOT NULL)::int + (person_id IS NOT NULL)::int = 1);

CREATE INDEX IF NOT EXISTS idx_approval_queue_person_id ON approval_queue(person_id);
