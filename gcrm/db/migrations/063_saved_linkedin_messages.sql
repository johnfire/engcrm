-- A private library of messages written by each user. No seeded content.
CREATE TABLE IF NOT EXISTS saved_linkedin_messages (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 100),
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 20000),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_saved_linkedin_messages_owner
    ON saved_linkedin_messages (workspace_id, user_id, updated_at DESC);
