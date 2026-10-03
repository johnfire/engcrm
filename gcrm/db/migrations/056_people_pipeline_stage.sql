-- A stage on the person themselves ("tag"): every LinkedIn connection starts as
-- a candidate and can be moved on by hand. Same vocabulary as organizations
-- (gcrm.organization_state.PIPELINE_STAGES). NULL = no stage set, which is how
-- people who are not LinkedIn connections stay until someone sets one. The
-- stage of the organization a person works at is a separate fact and stays on
-- the organization.
ALTER TABLE people ADD COLUMN IF NOT EXISTS pipeline_stage TEXT;

-- Everyone already imported from LinkedIn is a candidate. Only fills blanks, so
-- re-running never undoes a stage someone chose.
UPDATE people SET pipeline_stage = 'candidate'
 WHERE is_linkedin_contact AND pipeline_stage IS NULL AND deleted_at IS NULL;
