-- A newer LinkedIn export shows a different employer for someone we already
-- have. The importer never overwrites what is stored, so it records the change
-- here instead and a human decides (moved on / keep the old one).
--
-- pending_*           what the latest export shows, awaiting a decision
-- ignored_company_key normalized company the user said is NOT a real move
--                     ("keep"), so the next export doesn't flag it again
ALTER TABLE people ADD COLUMN IF NOT EXISTS pending_company_raw TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS pending_title       TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS pending_seen_at     TIMESTAMPTZ;
ALTER TABLE people ADD COLUMN IF NOT EXISTS ignored_company_key TEXT;

CREATE INDEX IF NOT EXISTS idx_people_company_change
    ON people (pending_seen_at) WHERE pending_company_raw IS NOT NULL AND deleted_at IS NULL;
