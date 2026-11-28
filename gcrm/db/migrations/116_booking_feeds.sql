-- Migration 116: several Proton busy-time links instead of one. Proton makes one "Share with anyone"
-- link per calendar and no combined feed, so each calendar that should block booking time gets its own
-- row here; free times are the open hours minus the busy time of all of them. Safe to run twice.

CREATE TABLE IF NOT EXISTS booking_feeds (
    id            SERIAL PRIMARY KEY,
    workspace_id  INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    label         TEXT NOT NULL CHECK (length(btrim(label)) BETWEEN 1 AND 60),
    -- The link carries the calendar's decryption key, so it is stored encrypted (as in migration 115).
    url_encrypted TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_booking_feeds_workspace ON booking_feeds (workspace_id);

DO $$
DECLARE
    default_workspace INTEGER;
BEGIN
    SELECT id INTO STRICT default_workspace FROM workspaces WHERE slug='default';
    EXECUTE format('ALTER TABLE booking_feeds ALTER COLUMN workspace_id SET DEFAULT COALESCE(request_workspace_id(),%s)',
                   default_workspace);
    -- The one link of migration 115 moves into the list, then its column goes: one place for feeds.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'booking_settings' AND column_name = 'feed_url_encrypted') THEN
        INSERT INTO booking_feeds (workspace_id, label, url_encrypted)
            SELECT workspace_id, 'Proton', feed_url_encrypted FROM booking_settings
            WHERE feed_url_encrypted IS NOT NULL;
        ALTER TABLE booking_settings DROP COLUMN feed_url_encrypted;
    END IF;
END $$;

ALTER TABLE booking_feeds ENABLE ROW LEVEL SECURITY;
ALTER TABLE booking_feeds FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS booking_feeds_workspace ON booking_feeds;
CREATE POLICY booking_feeds_workspace ON booking_feeds TO engcrm_workspace
    USING (workspace_id = request_workspace_id())
    WITH CHECK (workspace_id = request_workspace_id());
GRANT SELECT, INSERT, UPDATE, DELETE ON booking_feeds TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE booking_feeds_id_seq TO engcrm_workspace;
