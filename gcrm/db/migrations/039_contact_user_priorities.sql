-- Private per-user prospect priority. This is deliberately separate from the
-- shared agent fit/priority scores and from the shared starred flag.
UPDATE contacts
SET workspace_id = (SELECT id FROM workspaces WHERE slug = 'default')
WHERE workspace_id IS NULL;

CREATE TABLE IF NOT EXISTS contact_user_priorities (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    priority SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_contact_user_priorities_user_priority
    ON contact_user_priorities (user_id, priority);

CREATE INDEX IF NOT EXISTS idx_contact_user_priorities_contact
    ON contact_user_priorities (contact_id);
