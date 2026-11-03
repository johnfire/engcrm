-- The remote MCP connector (Claude from anywhere). See
-- docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md.
--
-- mcp_tokens: the secret a connector sends as "Authorization: Bearer ...". Only a
-- SHA-256 of it is stored; the token itself is shown once, when it is made
-- (scripts/mcp_token.py). Each token acts as one user, in that user's workspace.
CREATE TABLE IF NOT EXISTS mcp_tokens (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_sha256 TEXT        NOT NULL UNIQUE,
    label        TEXT        NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ
);

-- mcp_actions: what the connector saved, newest last, so "undo" can take back the
-- latest one. `before` holds what a change replaced (ratings, next steps); a record
-- the connector created needs none, undo soft-deletes it.
CREATE TABLE IF NOT EXISTS mcp_actions (
    id         BIGSERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT        NOT NULL CHECK (kind IN (
                   'organization_added', 'person_added', 'organization_activity', 'person_activity',
                   'organization_ratings', 'person_ratings', 'next_step')),
    target_id  INTEGER     NOT NULL,
    owner_id   INTEGER,     -- the organization or person an activity was logged on
    before     JSONB,
    summary    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    undone_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS mcp_actions_user_latest ON mcp_actions (user_id, id DESC) WHERE undone_at IS NULL;
