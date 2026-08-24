-- Migration 044: people_interactions
-- Timestamped, dictate-or-type note log per person. Mirrors `interactions`
-- (which is scoped to `contacts`/organizations) but for individuals. See
-- docs/plans/2026-08-24-people-interaction-log-design.md.

CREATE TABLE IF NOT EXISTS people_interactions (
    id          SERIAL PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    method      VARCHAR(20),
    note        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_people_interactions_person_id
    ON people_interactions(person_id) WHERE deleted_at IS NULL;
