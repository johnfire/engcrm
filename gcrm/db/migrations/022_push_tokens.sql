-- Device push-notification tokens (Expo Push) for the mobile app.
CREATE TABLE IF NOT EXISTS push_tokens (
    id         SERIAL PRIMARY KEY,
    token      TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
