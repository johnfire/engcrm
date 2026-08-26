-- Private per-user rating of an individual person's value as a contact —
-- deliberately separate from contact_user_priorities, which rates the
-- person's company, not the person themselves. Mirrors that table's shape.
CREATE TABLE IF NOT EXISTS person_user_priorities (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    priority SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, person_id)
);

CREATE INDEX IF NOT EXISTS idx_person_user_priorities_user_priority
    ON person_user_priorities (user_id, priority);

CREATE INDEX IF NOT EXISTS idx_person_user_priorities_person
    ON person_user_priorities (person_id);
