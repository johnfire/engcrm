-- User "favorite" star on contacts, toggled from the Contacts list and persisted.
-- Distinct from `flagged` (which marks contacts for review).
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS starred BOOLEAN NOT NULL DEFAULT FALSE;
