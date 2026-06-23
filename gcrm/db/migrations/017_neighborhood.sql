-- Neighborhood / sublocality for contacts, populated from Google Maps address
-- components and used for geographic targeting in cold-contact selection.
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS neighborhood TEXT;

CREATE INDEX IF NOT EXISTS idx_contacts_neighborhood
    ON contacts (neighborhood) WHERE deleted_at IS NULL;
