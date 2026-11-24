-- Stable identities let mobile records exist before their integer IDs are assigned.
ALTER TABLE contacts ADD COLUMN sync_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE people ADD COLUMN sync_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE deals ADD COLUMN sync_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE interactions ADD COLUMN sync_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE people_interactions ADD COLUMN sync_id UUID NOT NULL DEFAULT gen_random_uuid();

CREATE UNIQUE INDEX contacts_sync_id ON contacts (sync_id);
CREATE UNIQUE INDEX people_sync_id ON people (sync_id);
CREATE UNIQUE INDEX deals_sync_id ON deals (sync_id);
CREATE UNIQUE INDEX interactions_sync_id ON interactions (sync_id);
CREATE UNIQUE INDEX people_interactions_sync_id ON people_interactions (sync_id);
