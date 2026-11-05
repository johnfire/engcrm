CREATE TABLE web_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token_version INTEGER NOT NULL,
    admin_password_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK ((user_id IS NULL) = (admin_password_hash IS NOT NULL))
);
CREATE INDEX web_sessions_user ON web_sessions(user_id);
CREATE INDEX web_sessions_expiration ON web_sessions(expires_at);
