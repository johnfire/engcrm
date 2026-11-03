-- Field mode: where a user was, one row per point, while their phone's field mode was
-- on (a point every 5 minutes or 50 m). The newest point answers "where am I now" for
-- the remote MCP; all of them together are a travel history. Kept until the user
-- deletes them. See docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md.
CREATE TABLE IF NOT EXISTS field_locations (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    latitude    DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude   DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy_m  REAL             CHECK (accuracy_m >= 0),
    recorded_at TIMESTAMPTZ      NOT NULL,  -- when the phone took the fix
    received_at TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- A point sent twice (a retry after a dropped connection) is stored once.
    UNIQUE (user_id, recorded_at)
);

CREATE INDEX IF NOT EXISTS field_locations_user_time ON field_locations (user_id, recorded_at DESC);
