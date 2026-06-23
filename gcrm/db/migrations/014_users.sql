-- Per-user accounts for the web UI login (email + bcrypt password hash).
-- Supersedes the single shared ADMIN_PASSWORD/SPECTATOR_PASSWORD env logins;
-- ADMIN_PASSWORD is kept only as a transitional break-glass login (see auth.py).
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT        NOT NULL,
    name          TEXT        NOT NULL DEFAULT '',
    password_hash TEXT        NOT NULL,
    role          TEXT        NOT NULL DEFAULT 'admin'
                  CHECK (role IN ('admin', 'spectator')),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- Email is the login identifier: unique and matched case-insensitively.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (LOWER(email));
