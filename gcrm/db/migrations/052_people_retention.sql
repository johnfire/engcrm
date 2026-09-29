-- Migration 052: retention for people, and erasure that stays erased.
--
-- retention_hold      "keep this person": exempts them from the automatic purge
--                     of people idle for PEOPLE_RETENTION_DAYS (friends,
--                     collectors and other people you deliberately keep).
-- person_import_suppressions
--                     when a person is deleted by hand, the SHA-256 of their
--                     normalised LinkedIn URL is remembered here so the next
--                     Connections.csv import does not quietly bring them back.
--                     Only the hash is kept, never the URL or the name.

ALTER TABLE people ADD COLUMN IF NOT EXISTS retention_hold BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS person_import_suppressions (
    linkedin_url_hash TEXT PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
