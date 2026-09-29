-- Migration 051: LinkedIn connections as people.
--
-- A person can be marked as a LinkedIn connection whether they arrived through
-- the Connections.csv import or were typed in by hand, so the flag is separate
-- from `source` (which records only how the row was first created).
--   is_linkedin_contact  the mark itself
--   linkedin_url         profile URL — the import's dedup key
--   connected_on         the "Connected On" date from the export
--   company_raw          the company string exactly as LinkedIn has it; kept
--                        even after people.contact_id links the person to one
--                        of our organizations, so a mis-link can be re-checked
--
-- person_match_rejections remembers "this person does NOT work at that
-- organization" so a rejected suggestion never comes back on the review page.

ALTER TABLE people ADD COLUMN IF NOT EXISTS is_linkedin_contact BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE people ADD COLUMN IF NOT EXISTS linkedin_url        TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS connected_on        DATE;
ALTER TABLE people ADD COLUMN IF NOT EXISTS company_raw         TEXT;

CREATE INDEX IF NOT EXISTS idx_people_linkedin_url
    ON people(lower(linkedin_url)) WHERE linkedin_url IS NOT NULL;

-- "Who do I know at this organization?" and "who is still unlinked?" are both
-- LinkedIn-only lookups, so index just those rows.
CREATE INDEX IF NOT EXISTS idx_people_linkedin_contact_id
    ON people(contact_id) WHERE is_linkedin_contact;

CREATE TABLE IF NOT EXISTS person_match_rejections (
    person_id  INTEGER NOT NULL REFERENCES people(id)   ON DELETE CASCADE,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (person_id, contact_id)
);
