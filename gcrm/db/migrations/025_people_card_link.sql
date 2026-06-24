-- Issue #10: a scanned business card now also creates a `people` row for the
-- individual on it, linked to their company contact. Add the link plus the
-- card-carried fields the people table lacked (title, source).
ALTER TABLE people ADD COLUMN IF NOT EXISTS contact_id INTEGER REFERENCES contacts(id);
ALTER TABLE people ADD COLUMN IF NOT EXISTS title      TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS source     TEXT;

CREATE INDEX IF NOT EXISTS idx_people_contact_id  ON people(contact_id);
CREATE INDEX IF NOT EXISTS idx_people_email_lower ON people(lower(email));
